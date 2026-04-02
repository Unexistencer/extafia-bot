from __future__ import annotations

import asyncio
import html
from io import BytesIO
import re

import discord
import requests
from discord.ext import commands

from logger import generate_task_num, logger
from service import vhs as vhs_service


MAX_IMAGE_MB = 20
MAX_IMAGE_BYTES = MAX_IMAGE_MB * 1024 * 1024
URL_PATTERN = re.compile(r"https?://[^\s<>]+", re.IGNORECASE)
OPTION_RANGES = {
    "strength": (vhs_service.MIN_STRENGTH, vhs_service.MAX_STRENGTH),
    "noise": (vhs_service.MIN_NOISE, vhs_service.MAX_NOISE),
    "scanline": (vhs_service.MIN_SCANLINE, vhs_service.MAX_SCANLINE),
    "rgb_shift": (vhs_service.MIN_RGB_SHIFT, vhs_service.MAX_RGB_SHIFT),
    "lofi": (vhs_service.MIN_LOFI, vhs_service.MAX_LOFI),
}


class VhsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @staticmethod
    def _usage_text() -> str:
        return (
            "Usage: `.vhs [strength] [noise=0-100] [scanline=0-1000] "
            "[rgb=0-200] [noisebar] [lofi|lofi=1-100]`"
        )

    @staticmethod
    async def _send_error_embed(target: commands.Context, message: str) -> None:
        embed = discord.Embed(
            title="VHS Processing Failed",
            description=message,
            color=discord.Color.red(),
        )
        await target.send(embed=embed)

    @staticmethod
    def _parse_options(raw: str | None) -> dict[str, int | bool | None]:
        parsed: dict[str, int | bool | None] = {
            "strength": None,
            "noise": None,
            "scanline": None,
            "rgb_shift": None,
            "noise_bar": False,
            "lofi": None,
        }

        if raw is None or not raw.strip():
            return parsed

        aliases = {
            "strength": "strength",
            "noise": "noise",
            "scan": "scanline",
            "scanline": "scanline",
            "rgb": "rgb_shift",
            "rgbshift": "rgb_shift",
            "rgb_shift": "rgb_shift",
            "lofi": "lofi",
            "lowfi": "lofi",
        }

        tokens = raw.split()
        for index, token in enumerate(tokens):
            lowered = token.strip().lower()
            if lowered in {"noisebar", "noise_bar"}:
                parsed["noise_bar"] = True
                continue
            if lowered in {"lofi", "lowfi"}:
                parsed["lofi"] = vhs_service.DEFAULT_LOFI
                continue

            if "=" not in token:
                if index == 0:
                    key = "strength"
                    value = token
                else:
                    raise ValueError(VhsCog._usage_text())
            else:
                raw_key, value = token.split("=", 1)
                key = aliases.get(raw_key.strip().lower())
                if key is None:
                    raise ValueError(
                        "Unknown option. Supported: strength, noise, scanline, rgb, noisebar, lofi."
                    )

            try:
                number = int(value.strip())
            except ValueError as exc:
                raise ValueError("All VHS options must be integers.") from exc

            minimum, maximum = OPTION_RANGES[key]
            if number < minimum:
                raise ValueError(f"`{key.replace('_shift', '')}` must be between {minimum} and {maximum}.")

            parsed[key] = number

        return parsed

    @staticmethod
    def _looks_like_direct_media_url(url: str | None) -> bool:
        if not url:
            return False
        lowered = url.lower()
        return any(ext in lowered for ext in (".gif", ".png", ".jpg", ".jpeg", ".webp"))

    @classmethod
    def _media_url_priority(cls, url: str | None) -> int:
        if not url:
            return -1
        lowered = url.lower()
        if ".gif" in lowered:
            return 4
        if ".webp" in lowered:
            return 3
        if "media.tenor.com" in lowered:
            return 2
        if ".png" in lowered or ".jpg" in lowered or ".jpeg" in lowered:
            return 1
        return 0

    @staticmethod
    def _is_page_url(url: str | None) -> bool:
        if not url:
            return False
        lowered = url.lower()
        return any(
            token in lowered
            for token in (
                "tenor.com/view/",
                "imgur.com/",
                "giphy.com/",
            )
        )

    @staticmethod
    def _is_animated_preview_url(url: str | None) -> bool:
        if not url:
            return False
        lowered = url.lower()
        return (
            lowered.startswith("https://media.tenor.com/")
            and lowered.endswith((".png", ".jpg", ".jpeg"))
        )

    @classmethod
    def _pick_embed_image_url(cls, embeds: list[discord.Embed]) -> str | None:
        best_url: str | None = None
        best_score = -1

        def consider(candidate: str | None) -> None:
            nonlocal best_url, best_score
            if not cls._looks_like_direct_media_url(candidate):
                return
            score = cls._media_url_priority(candidate)
            if score > best_score:
                best_url = candidate
                best_score = score

        for embed in embeds:
            consider(embed.image.url if embed.image else None)
            consider(embed.image.proxy_url if embed.image else None)
            consider(embed.thumbnail.url if embed.thumbnail else None)
            consider(embed.thumbnail.proxy_url if embed.thumbnail else None)

            payload = embed.to_dict()
            for key in ("video", "image", "thumbnail"):
                media = payload.get(key) or {}
                for field in ("url", "proxy_url"):
                    consider(media.get(field))

            for field in ("url",):
                consider(payload.get(field))
        return best_url

    @staticmethod
    def _pick_content_image_url(content: str | None) -> str | None:
        if not content:
            return None
        match = URL_PATTERN.search(content)
        if not match:
            return None
        return match.group(0)

    @staticmethod
    def _pick_message_attachment(message: discord.Message) -> discord.Attachment | None:
        for attachment in message.attachments:
            filename = (attachment.filename or "").lower()
            if (
                attachment.content_type and attachment.content_type.startswith("image/")
            ) or filename.endswith((".gif", ".png", ".jpg", ".jpeg", ".webp")):
                return attachment
        return None

    async def _find_recent_source(
        self,
        channel: discord.abc.Messageable,
        before_message: discord.Message,
        max_messages: int = 30,
    ) -> tuple[discord.Attachment | None, str | None, str | None, str | None]:
        if not hasattr(channel, "history"):
            return None, None, None, None

        try:
            async for message in channel.history(limit=max_messages, before=before_message):
                attachment = self._pick_message_attachment(message)
                if attachment is not None:
                    return attachment, None, None, "history_attachment"

                embed_url = self._pick_embed_image_url(message.embeds)
                content_url = self._pick_content_image_url(message.content)
                if self._is_page_url(content_url) and self._is_animated_preview_url(embed_url):
                    logger.info(f".vhs preferring history page URL over animated preview: {content_url} <- {embed_url}")
                    embed_url = None

                if embed_url is not None:
                    return None, embed_url, None, "history_embed"

                if content_url is not None:
                    return None, None, content_url, "history_content_url"
        except Exception:
            return None, None, None, None

        return None, None, None, None

    @staticmethod
    def _validate_image_size(size: int | None) -> None:
        if size and size > MAX_IMAGE_BYTES:
            raise ValueError(f"Image is too large. Please use an image under {MAX_IMAGE_MB}MB.")

    async def _read_attachment_bytes(self, attachment: discord.Attachment) -> tuple[bytes, str]:
        filename = (attachment.filename or "").lower()
        if (
            not attachment.content_type
            or not attachment.content_type.startswith("image/")
        ) and not filename.endswith((".gif", ".png", ".jpg", ".jpeg", ".webp")):
            raise ValueError("That attachment is not an image. Please try again with an image.")

        self._validate_image_size(attachment.size)

        try:
            data = await attachment.read()
        except Exception as exc:
            raise ValueError("Failed to read the image. Please re-upload it and try again.") from exc

        self._validate_image_size(len(data))
        return data, attachment.filename or "image"

    @staticmethod
    def _extract_media_url_from_page(page_text: str) -> str | None:
        patterns = (
            r'"contentUrl":"(https:[^"]+?\.(?:gif|webp)(?:\?[^"]*)?)"',
            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+?\.(?:gif|webp)(?:\?[^"\']*)?)["\']',
            r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+?\.(?:gif|webp)(?:\?[^"\']*)?)["\']',
            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
            r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']',
            r'"contentUrl":"(https:[^"]+)"',
        )
        for pattern in patterns:
            match = re.search(pattern, page_text, re.IGNORECASE)
            if match:
                return html.unescape(match.group(1)).replace("\\u002F", "/").replace("\\/", "/")
        return None

    @classmethod
    def _download_image(cls, url: str) -> tuple[bytes, str]:
        response = requests.get(url, timeout=15)
        response.raise_for_status()

        content_type = response.headers.get("Content-Type", "")
        if "text/html" in content_type:
            resolved = cls._extract_media_url_from_page(response.text)
            if resolved and resolved != url:
                return cls._download_image(resolved)

        if content_type and not content_type.startswith("image/"):
            raise ValueError("The found content is not an image. Please upload an image directly.")

        data = response.content
        if len(data) > MAX_IMAGE_BYTES:
            raise ValueError(f"Image is too large. Please use an image under {MAX_IMAGE_MB}MB.")

        filename = url.rsplit("/", 1)[-1].split("?", 1)[0] or "image"
        return data, filename

    async def _resolve_source(self, message: discord.Message) -> tuple[bytes, str]:
        attachment = self._pick_message_attachment(message)
        embed_image_url = self._pick_embed_image_url(message.embeds)
        content_image_url = self._pick_content_image_url(message.content)
        source_label = "message_attachment" if attachment is not None else None

        if (
            attachment is None
            and content_image_url is not None
            and self._is_page_url(content_image_url)
            and self._is_animated_preview_url(embed_image_url)
        ):
            logger.info(
                f".vhs preferring page URL over animated preview: {content_image_url} <- {embed_image_url}"
            )
            embed_image_url = None

        if attachment is None and embed_image_url is None and content_image_url is None and message.reference and message.reference.message_id:
            try:
                ref_message = await message.channel.fetch_message(message.reference.message_id)
            except Exception:
                ref_message = None

            if ref_message is not None:
                if ref_message.attachments:
                    attachment = ref_message.attachments[0]
                    source_label = "reply_attachment"
                if embed_image_url is None:
                    embed_image_url = self._pick_embed_image_url(ref_message.embeds)
                    if embed_image_url is not None:
                        source_label = "reply_embed"
                if content_image_url is None:
                    content_image_url = self._pick_content_image_url(ref_message.content)
                    if content_image_url is not None:
                        source_label = "reply_content_url"

                if (
                    attachment is None
                    and content_image_url is not None
                    and self._is_page_url(content_image_url)
                    and self._is_animated_preview_url(embed_image_url)
                ):
                    logger.info(
                        f".vhs preferring reply page URL over animated preview: {content_image_url} <- {embed_image_url}"
                    )
                    embed_image_url = None

        if attachment is None and embed_image_url is not None and source_label is None:
            source_label = "message_embed"
        if attachment is None and embed_image_url is None and content_image_url is not None and source_label is None:
            source_label = "message_content_url"

        if attachment is None and embed_image_url is None and content_image_url is None:
            attachment, embed_image_url, content_image_url, source_label = await self._find_recent_source(
                message.channel,
                message,
            )

        if attachment is not None:
            logger.info(f".vhs source resolved via {source_label or 'attachment'}")
            return await self._read_attachment_bytes(attachment)

        if embed_image_url is not None:
            logger.info(f".vhs source resolved via {source_label or 'embed'}: {embed_image_url}")
            return await asyncio.to_thread(self._download_image, embed_image_url)

        if content_image_url is not None:
            logger.info(f".vhs source resolved via {source_label or 'content_url'}: {content_image_url}")
            return await asyncio.to_thread(self._download_image, content_image_url)

        logger.info(".vhs source resolution failed: no attachment, embed, or URL found")
        raise ValueError("No image found. Attach an image, reply to an image, or run `.vhs` after a recent image.")

    @commands.command(name="vhs")
    async def vhs_prefix(self, ctx: commands.Context, *, options: str = ""):
        async with ctx.typing():
            task_num = generate_task_num()
            guild_id = ctx.guild.id if ctx.guild else 0

            logger.info(
                f"[{task_num}] .vhs invoked by {ctx.author} #{ctx.author.id} "
                f"in guild {ctx.guild} #{guild_id}"
            )

            try:
                parsed_options = self._parse_options(options)
                image_bytes, source_name = await self._resolve_source(ctx.message)
                output_bytes, output_extension = await asyncio.to_thread(
                    vhs_service.apply_vhs_effect,
                    image_bytes,
                    parsed_options["strength"],
                    parsed_options["noise"],
                    parsed_options["scanline"],
                    parsed_options["rgb_shift"],
                    parsed_options["noise_bar"],
                    parsed_options["lofi"],
                )
            except ValueError as exc:
                await self._send_error_embed(ctx, str(exc))
                return
            except Exception:
                logger.exception(f"[{task_num}] .vhs failed unexpectedly")
                await self._send_error_embed(ctx, "VHS processing failed. Please try a different image.")
                return

            filename = vhs_service.build_output_filename(source_name, output_extension)
            file = discord.File(BytesIO(output_bytes), filename=filename)
            await ctx.send(file=file)


async def setup(bot: commands.Bot):
    await bot.add_cog(VhsCog(bot))
