from __future__ import annotations

import discord
from discord.ext import commands
from discord import app_commands, Interaction

from service.help_service import HelpService

from logger import logger, generate_task_num


class HelpCog(commands.Cog):
    def __init__(self, bot: commands.Bot, svc: HelpService):
        self.bot = bot
        self.svc = svc

    @app_commands.command(name="h", description="Show available commands")
    async def info(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)
        await self._run_help(
            task_num=generate_task_num(),
            guild_id=interaction.guild.id,
            user_id=interaction.user.id,
            actor=str(interaction.user),
            guild=str(interaction.guild),
            send_embed=lambda embed: interaction.edit_original_response(embed=embed),
        )

    @commands.command(name="h")
    async def info_prefix(self, ctx: commands.Context):
        async with ctx.typing():
            await self._run_help(
                task_num=generate_task_num(),
                guild_id=ctx.guild.id if ctx.guild else 0,
                user_id=ctx.author.id,
                actor=str(ctx.author),
                guild=str(ctx.guild),
                send_embed=lambda embed: ctx.send(embed=embed),
            )

    async def _run_help(self, task_num: str, guild_id: int, user_id: int, actor: str, guild: str, send_embed):
        logger.info(
            f"[{task_num}]help invoked by {actor} #{user_id} "
            f"in guild {guild} #{guild_id}"
        )

        embed = await self.svc.build_help_embed(
            guild_id=guild_id,
            user_id=user_id,
        )
        logger.info(f"[{task_num}]Embed done.")
        await send_embed(embed)


async def setup(bot: commands.Bot):
    svc = HelpService()
    await bot.add_cog(HelpCog(bot, svc))
