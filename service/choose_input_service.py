from __future__ import annotations
import asyncio
import hashlib
from urllib.parse import urlparse
from typing import Optional, List

import discord
import requests

import service.ocr_service
from constants import Category
from logger import logger
from msg_utils import MessageResolver

MAX_IMAGE_MB = 5
MAX_IMAGE_BYTES = MAX_IMAGE_MB * 1024 * 1024
MAX_DESC = 3900

_OCR_CACHE: dict[str, list[str]] = {}


class ChooseInputError(Exception):
    """Use-case input error"""

    def __init__(self, user_message: str):
        super().__init__(user_message)
        self.user_message = user_message


async def _choose_message(guild_id: int, user_id: int, *keys, **kwargs) -> str:
    resolver = MessageResolver(guild_id, user_id)
    return await resolver.get(Category.CHOOSE, *keys, **kwargs)


async def build_options_embed(guild_id: int, user_id: int, items: list[str]) -> discord.Embed:
    lines = [f"{i+1}. {w}" for i, w in enumerate(items)]
    desc = "\n".join(lines)
    if len(desc) > MAX_DESC:
        suffix = await _choose_message(guild_id, user_id, "ui", "options_truncated")
        desc = desc[:MAX_DESC] + "\n" + suffix
    title = await _choose_message(guild_id, user_id, "ui", "options")
    return discord.Embed(
        title=title,
        description=desc,
        color=discord.Color.blurple(),
    )


def _dedupe_keep_order(items: List[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for it in items:
        it = (it or "").strip()
        if not it:
            continue
        if it in seen:
            continue
        out.append(it)
        seen.add(it)
    return out


def parse_text_options(options: Optional[str]) -> List[str]:
    """text options -> items"""
    if not options:
        return []
    raw = options.replace("\u3000", " ").strip()
    parts = [p.strip() for p in raw.split(" ") if p.strip()]
    return _dedupe_keep_order(parts)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


async def _validate_image_attachment(att: discord.Attachment, guild_id: int, user_id: int) -> None:
    if not att.content_type or not att.content_type.startswith("image/"):
        raise ChooseInputError(await _choose_message(guild_id, user_id, "error", "not_image"))
    if att.size and att.size > MAX_IMAGE_BYTES:
        raise ChooseInputError(
            await _choose_message(guild_id, user_id, "error", "image_too_large", max_mb=MAX_IMAGE_MB)
        )


def _suffix_from_filename(filename: str) -> str:
    if "." in filename:
        ext = filename.rsplit(".", 1)[-1].lower()
        if ext:
            return f".{ext}"
    return ".png"


def _suffix_from_url(url: str) -> str:
    path = urlparse(url).path
    if "." in path:
        ext = path.rsplit(".", 1)[-1].lower()
        if ext and len(ext) <= 5:
            return f".{ext}"
    return ".png"


def _pick_image_url_from_embeds(embeds: List[discord.Embed]) -> Optional[str]:
    for em in embeds:
        if em.thumbnail and em.thumbnail.url:
            return em.thumbnail.url
        if em.image and em.image.url:
            return em.image.url
    return None


async def ocr_items_from_attachment(att: discord.Attachment, guild_id: int, user_id: int) -> List[str]:
    """Attachment -> OCR items"""
    await _validate_image_attachment(att, guild_id, user_id)

    try:
        data = await att.read()
    except Exception:
        raise ChooseInputError(await _choose_message(guild_id, user_id, "error", "image_read_failed"))

    h = _sha256(data)
    cached = _OCR_CACHE.get(h)
    if cached is not None:
        logger.info(f"[choose-ocr] Cache hit for attachment '{att.filename}' -> {cached}")
        return cached

    try:
        items = await asyncio.to_thread(
            service.ocr_service.extract_options_from_bytes,
            data,
            suffix=_suffix_from_filename(att.filename),
        )
    except Exception:
        raise ChooseInputError(await _choose_message(guild_id, user_id, "error", "ocr_failed"))

    items = _dedupe_keep_order(items)
    logger.info(f"[choose-ocr] Attachment '{att.filename}' deduped to {len(items)} options: {items}")
    _OCR_CACHE[h] = items
    return items


def _download_image_bytes(url: str) -> tuple[bytes, Optional[str], Optional[int]]:
    r = requests.get(url, timeout=10)
    r.raise_for_status()

    content_type = r.headers.get("Content-Type")
    content_length = r.headers.get("Content-Length")
    size = int(content_length) if content_length and content_length.isdigit() else None
    return r.content, content_type, size


async def ocr_items_from_image_url(url: str, guild_id: int, user_id: int) -> List[str]:
    try:
        data, content_type, declared_size = await asyncio.to_thread(_download_image_bytes, url)
    except Exception:
        raise ChooseInputError(await _choose_message(guild_id, user_id, "error", "image_read_failed"))

    if content_type and not content_type.startswith("image/"):
        raise ChooseInputError(await _choose_message(guild_id, user_id, "error", "not_image"))

    real_size = len(data)
    if (declared_size and declared_size > MAX_IMAGE_BYTES) or real_size > MAX_IMAGE_BYTES:
        raise ChooseInputError(
            await _choose_message(guild_id, user_id, "error", "image_too_large", max_mb=MAX_IMAGE_MB)
        )

    h = _sha256(data)
    cached = _OCR_CACHE.get(h)
    if cached is not None:
        logger.info(f"[choose-ocr] Cache hit for image url '{url}' -> {cached}")
        return cached

    try:
        items = await asyncio.to_thread(
            service.ocr_service.extract_options_from_bytes,
            data,
            suffix=_suffix_from_url(url),
        )
    except Exception:
        raise ChooseInputError(await _choose_message(guild_id, user_id, "error", "ocr_failed"))

    items = _dedupe_keep_order(items)
    logger.info(f"[choose-ocr] Image url '{url}' deduped to {len(items)} options: {items}")
    _OCR_CACHE[h] = items
    return items


async def find_recent_image_attachment(
    *,
    channel: discord.abc.Messageable,
    before_message: discord.Message,
    max_messages: int = 50,
) -> Optional[discord.Attachment]:
    """
    slim last message with image and ocr
    """
    if not hasattr(channel, "history"):
        return None

    try:
        async for msg in channel.history(limit=max_messages, before=before_message):
            if not msg.attachments:
                continue
            for att in msg.attachments:
                if att.content_type and att.content_type.startswith("image/"):
                    return att
    except Exception:
        return None

    return None


async def find_recent_embed_image_url(
    *,
    channel: discord.abc.Messageable,
    before_message: discord.Message,
    max_messages: int = 50,
) -> Optional[str]:
    if not hasattr(channel, "history"):
        return None

    try:
        async for msg in channel.history(limit=max_messages, before=before_message):
            if not msg.embeds:
                continue
            url = _pick_image_url_from_embeds(msg.embeds)
            if url:
                return url
    except Exception:
        return None

    return None


async def resolve_items_from_interaction(
    *,
    guild_id: int,
    user_id: int,
    options: Optional[str],
    image: Optional[discord.Attachment],
) -> List[str]:
    """
    Slash /choose input
    - if image exists -> OCR items
    - merge options in command
    """
    items: List[str] = []

    if image is not None:
        items.extend(await ocr_items_from_attachment(image, guild_id, user_id))

    items.extend(parse_text_options(options))
    items = _dedupe_keep_order(items)

    return items


async def resolve_items_from_message(
    *,
    guild_id: int,
    user_id: int,
    message: discord.Message,
    channel: discord.abc.Messageable,
    options: Optional[str],
) -> List[str]:
    """
    .choose (non-slash command)
    Priority:
    1) attachment in msg
    2) embed image/thumbnail in msg
    3) image source in replied msg (attachment/embed)
    4) latest image source in recent msgs (attachment/embed)
    5) text options
    """
    items: List[str] = []

    att: Optional[discord.Attachment] = message.attachments[0] if message.attachments else None
    embed_image_url: Optional[str] = _pick_image_url_from_embeds(message.embeds)

    if att is None and message.reference and message.reference.message_id:
        try:
            ref_msg = await channel.fetch_message(message.reference.message_id)
            if ref_msg.attachments:
                att = ref_msg.attachments[0]
            if embed_image_url is None:
                embed_image_url = _pick_image_url_from_embeds(ref_msg.embeds)
        except Exception:
            pass

    text_items = parse_text_options(options)
    if att is None and embed_image_url is None and not text_items:
        att = await find_recent_image_attachment(channel=channel, before_message=message, max_messages=30)
        if att is None:
            embed_image_url = await find_recent_embed_image_url(channel=channel, before_message=message, max_messages=30)

    if att is not None:
        items.extend(await ocr_items_from_attachment(att, guild_id, user_id))
    elif embed_image_url is not None:
        items.extend(await ocr_items_from_image_url(embed_image_url, guild_id, user_id))

    items.extend(parse_text_options(options))
    items = _dedupe_keep_order(items)

    return items
