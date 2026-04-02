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
        task_num = generate_task_num()
        logger.info(
            f"[{task_num}]help invoked by {interaction.user} #{interaction.user.id} "
            f"in guild {interaction.guild} #{interaction.guild.id}"
        )

        await interaction.response.defer(ephemeral=True)

        embed = await self.svc.build_help_embed(
            guild_id=interaction.guild.id,
            user_id=interaction.user.id,
        )
        logger.info(f"[{task_num}]Embed done.")

        await interaction.edit_original_response(embed=embed)


async def setup(bot: commands.Bot):
    svc = HelpService()
    await bot.add_cog(HelpCog(bot, svc))
