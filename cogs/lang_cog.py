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
            app_commands.Choice(name='en', value="English"),
            app_commands.Choice(name='zh', value="Traditional Chinese(Written Cantonese)"),
            app_commands.Choice(name='jp', value="Japanese"),
        ]
    )
    
    async def lang(self, interaction: Interaction, code: app_commands.Choice[str] | None = None):
        task_num = generate_task_num()
        logger.info(f"[{task_num}]Lang invoked by {interaction.user} #{interaction.user.id} "
                    f"in guild {interaction.guild} #{interaction.guild.id} lang_code={code.name}")

        await interaction.response.defer(ephemeral=True)

        lang_code = code.name

        embed = await self.svc.change_language(
            task_num=task_num,
            guild_id=interaction.guild.id,
            user_id=interaction.user.id,
            lang_code=lang_code,
        )
        logger.info(f"[{task_num}]Embed done.")
        await interaction.edit_original_response(embed=embed)


async def setup(bot: commands.Bot):
    svc = LangService()
    await bot.add_cog(LangCog(bot, svc))
