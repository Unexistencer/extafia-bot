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
        target = interaction.user
        task_num = generate_task_num()
        logger.info(
            f"[{task_num}]stat invoked by {interaction.user} #{interaction.user.id} "
            f"in guild {interaction.guild} #{interaction.guild.id}"
            )

        await interaction.response.defer(ephemeral=False)

        embeds = await self.svc.build_status_embeds(
            task_num=task_num,
            guild_id=interaction.guild.id,
            user_id=target.id,
            display_name=target.display_name,
        )

        view = PagedView(embeds, owner_id=interaction.user.id)
        logger.info(f"[{task_num}]Embed done.")
        await interaction.followup.send(embed=embeds[0], view=view)

async def setup(bot: commands.Bot):
    svc = StatusService()
    await bot.add_cog(StatusCog(bot, svc))
