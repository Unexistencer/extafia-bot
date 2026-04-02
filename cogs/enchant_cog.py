from __future__ import annotations

import discord
from discord.ext import commands, tasks
from discord import app_commands, Interaction
from service.enchant_service import EnchantService, EnchantPayload

from logger import logger, generate_task_num


class EnchantCog(commands.Cog):
    def __init__(self, bot: commands.Bot, svc: EnchantService):
        self.bot = bot
        self.svc = svc
        self.cache = svc.cache
        self._flusher.start()

    def cog_unload(self):
        self._flusher.cancel()

    @tasks.loop(seconds=20)
    async def _flusher(self):
        await self.svc.flush_due()

    @_flusher.before_loop
    async def _before(self):
        await self.bot.wait_until_ready()

    @app_commands.command(name="enchant", description="Beautify your cock")
    @app_commands.describe(action="[optional]show: show current enchantments")
    @app_commands.choices(
        action=[
            app_commands.Choice(name="show", value="show"),
        ]
    )
    async def enchant(self, interaction: Interaction, action: app_commands.Choice[str] | None = None):
        task_num = generate_task_num()
        logger.info(
            f"[{task_num}]enchant invoked by {interaction.user} #{interaction.user.id} "
            f"in guild {interaction.guild} #{interaction.guild.id}"
            )
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild.id if interaction.guild else 0
        user_id = interaction.user.id
        try:
            act = action.value
        except:
            act = "roll"

        
        if act == "show":
            logger.info(f"[{task_num}]Show enchantments status.")
            payload = await self.svc.show_status(task_num, guild_id, user_id)
        else:
            logger.info(f"[{task_num}]Roll enchantments.")
            payload = await self.svc.roll(task_num, guild_id, user_id)

        embed = self._to_embed(payload)
        view  = EnchantView(self.svc, guild_id, user_id, self._to_embed)
        logger.info(f"[{task_num}]Embed done.")
        await interaction.edit_original_response(embed=embed, view=view)

    def _to_embed(self, p: EnchantPayload) -> discord.Embed:
        color = p.color_hint if p.color_hint is not None else discord.Color.greyple().value
        return discord.Embed(title=p.title, description=p.description, color=color)

class EnchantView(discord.ui.View):
    def __init__(self, svc: EnchantService, guild_id: int, user_id: int, render):
        super().__init__(timeout=180)   # wait-time
        self.svc = svc
        self.guild_id = guild_id
        self.user_id = user_id
        self.render = render

    async def on_timeout(self):
        # flush user if View disable
        await self.svc.flush_user(self.guild_id, self.user_id)

    async def _guard_user(self, interaction: Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("?", ephemeral=True)
            return False
        return True

    @discord.ui.button(emoji="<:shingcoin_2:952962920940200026>", label="x10 Retry", style=discord.ButtonStyle.primary, custom_id="enchant_reroll")
    async def btn_reroll(self, interaction: Interaction, button: discord.ui.Button):
        task_num = generate_task_num()
        logger.info(
            f"[{task_num}]enchant->enchant invoked by {interaction.user} #{interaction.user.id} "
            f"in guild {interaction.guild} #{interaction.guild.id}"
            )
        if not await self._guard_user(interaction):
            return
        await interaction.response.defer(ephemeral=True)

        logger.info(f"[{task_num}]Roll enchantments.")
        payload = await self.svc.roll(task_num, self.guild_id, self.user_id)
        embed = self.render(payload)
        logger.info(f"[{task_num}]Enchant started.")

        await interaction.followup.edit_message(
            message_id=interaction.message.id,
            embed=embed,
            view=self
        )

    @discord.ui.button(emoji="<:shingcoin_1:952960803663937577>", label="x1 Vaal", style=discord.ButtonStyle.danger, custom_id="enchant_vaal")
    async def btn_vaal(self, interaction: Interaction, button: discord.ui.Button):
        task_num = generate_task_num()
        logger.info(
            f"[{task_num}]enchant->vaal invoked by {interaction.user} #{interaction.user.id} "
            f"in guild {interaction.guild} #{interaction.guild.id}"
            )
        if not await self._guard_user(interaction):
            return
        await interaction.response.defer(ephemeral=True)

        logger.info(f"[{task_num}]Vaal started.")
        payload = await self.svc.vaal(task_num, self.guild_id, self.user_id)
        embed = self.render(payload)
        logger.info(f"[{task_num}]Vaal done.")

        await interaction.followup.edit_message(
            message_id=interaction.message.id,
            embed=embed,
            view=None
        )

async def setup(bot: commands.Bot):
    svc = getattr(bot, "enchant_service", None)
    if svc is None:
        from service.cache import EnchantCache
        from service.enchant_service import EnchantService
        cache = EnchantCache(ttl_sec=30)
        svc = EnchantService(cache)
    await bot.add_cog(EnchantCog(bot, svc))
