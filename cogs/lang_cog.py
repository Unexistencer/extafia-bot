from __future__ import annotations

import discord
from discord.ext import commands
from discord import app_commands, Interaction

from service.lang_service import LangService

from logger import logger, generate_task_num


class LangCog(commands.Cog):
    def __init__(self, bot: commands.Bot, svc: LangService):
        self.bot = bot
        self.svc = svc

    @app_commands.command(name="lang", description="Show or change language")
    @app_commands.describe(code="[optional]Language to change or skip option to show current language")
    @app_commands.choices(
        code=[
            app_commands.Choice(name="en", value="English"),
            app_commands.Choice(name="zh", value="Traditional Chinese(Written Cantonese)"),
            app_commands.Choice(name="jp", value="Japanese"),
        ]
    )
    async def lang(self, interaction: Interaction, code: app_commands.Choice[str] | None = None):
        await interaction.response.defer(ephemeral=True)
        await self._run_lang(
            task_num=generate_task_num(),
            guild_id=interaction.guild.id,
            user_id=interaction.user.id,
            actor=str(interaction.user),
            guild=str(interaction.guild),
            lang_code=code.name if code else None,
            send_embed=lambda embed: interaction.edit_original_response(embed=embed),
        )

    @commands.command(name="lang")
    async def lang_prefix(self, ctx: commands.Context, code: str | None = None):
        async with ctx.typing():
            await self._run_lang(
                task_num=generate_task_num(),
                guild_id=ctx.guild.id if ctx.guild else 0,
                user_id=ctx.author.id,
                actor=str(ctx.author),
                guild=str(ctx.guild),
                lang_code=code.lower() if code else None,
                send_embed=lambda embed: ctx.send(embed=embed),
            )

    async def _run_lang(self, task_num: str, guild_id: int, user_id: int, actor: str, guild: str, lang_code: str | None, send_embed):
        logger.info(
            f"[{task_num}]Lang invoked by {actor} #{user_id} "
            f"in guild {guild} #{guild_id} lang_code={lang_code}"
        )

        embed = await self.svc.change_language(
            task_num=task_num,
            guild_id=guild_id,
            user_id=user_id,
            lang_code=lang_code,
        )
        logger.info(f"[{task_num}]Embed done.")
        await send_embed(embed)


async def setup(bot: commands.Bot):
    svc = LangService()
    await bot.add_cog(LangCog(bot, svc))
