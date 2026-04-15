from __future__ import annotations

import discord
from discord.ext import commands
from discord import app_commands, Interaction

from service.stat_service import StatusService
from msg_utils import PagedView

from logger import logger, generate_task_num


class StatusCog(commands.Cog):
    def __init__(self, bot: commands.Bot, svc: StatusService):
        self.bot = bot
        self.svc = svc

    @app_commands.command(name="stat", description="Show current status")
    async def stat(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=False)
        await self._run_stat(
            task_num=generate_task_num(),
            guild_id=interaction.guild.id,
            actor_id=interaction.user.id,
            actor=str(interaction.user),
            guild=str(interaction.guild),
            target=interaction.user,
            send_result=lambda embed, view: interaction.followup.send(embed=embed, view=view),
        )

    @commands.command(name="stat")
    async def stat_prefix(self, ctx: commands.Context):
        async with ctx.typing():
            await self._run_stat(
                task_num=generate_task_num(),
                guild_id=ctx.guild.id if ctx.guild else 0,
                actor_id=ctx.author.id,
                actor=str(ctx.author),
                guild=str(ctx.guild),
                target=ctx.author,
                send_result=lambda embed, view: ctx.send(embed=embed, view=view),
            )

    async def _run_stat(self, task_num: str, guild_id: int, actor_id: int, actor: str, guild: str, target: discord.abc.User, send_result):
        logger.info(
            f"[{task_num}]stat invoked by {actor} #{actor_id} "
            f"in guild {guild} #{guild_id}"
        )

        embeds = await self.svc.build_status_embeds(
            task_num=task_num,
            guild_id=guild_id,
            user_id=target.id,
            display_name=target.display_name,
        )

        view = PagedView(embeds, owner_id=actor_id)
        logger.info(f"[{task_num}]Embed done.")
        await send_result(embeds[0], view)


async def setup(bot: commands.Bot):
    svc = StatusService()
    await bot.add_cog(StatusCog(bot, svc))
