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
        await interaction.response.defer(ephemeral=True)
        await self._run_enchant(
            task_num=generate_task_num(),
            guild_id=interaction.guild.id if interaction.guild else 0,
            user_id=interaction.user.id,
            actor=str(interaction.user),
            guild=str(interaction.guild),
            action_value=action.value if action else "roll",
            send_result=lambda embed, view: interaction.edit_original_response(embed=embed, view=view),
        )

    @commands.command(name="enchant")
    async def enchant_prefix(self, ctx: commands.Context, action: str | None = None):
        async with ctx.typing():
            await self._run_enchant(
                task_num=generate_task_num(),
                guild_id=ctx.guild.id if ctx.guild else 0,
                user_id=ctx.author.id,
                actor=str(ctx.author),
                guild=str(ctx.guild),
                action_value=(action or "roll").lower(),
                send_result=lambda embed, view: ctx.send(embed=embed, view=view),
            )

    async def _run_enchant(self, task_num: str, guild_id: int, user_id: int, actor: str, guild: str, action_value: str, send_result):
        logger.info(
            f"[{task_num}]enchant invoked by {actor} #{user_id} "
            f"in guild {guild} #{guild_id}"
        )

        if action_value == "show":
            logger.info(f"[{task_num}]Show enchantments status.")
            payload = await self.svc.show_status(task_num, guild_id, user_id)
        else:
            logger.info(f"[{task_num}]Roll enchantments.")
            payload = await self.svc.roll(task_num, guild_id, user_id)

        embed = self._to_embed(payload)
        view = EnchantView(self.svc, guild_id, user_id, self._to_embed)
        logger.info(f"[{task_num}]Embed done.")
        await send_result(embed, view)

    def _to_embed(self, p: EnchantPayload) -> discord.Embed:
        color = p.color_hint if p.color_hint is not None else discord.Color.greyple().value
        return discord.Embed(title=p.title, description=p.description, color=color)


class EnchantView(discord.ui.View):
    def __init__(self, svc: EnchantService, guild_id: int, user_id: int, render):
        super().__init__(timeout=180)
        self.svc = svc
        self.guild_id = guild_id
        self.user_id = user_id
        self.render = render

    async def on_timeout(self):
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
            view=self,
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
            view=None,
        )


async def setup(bot: commands.Bot):
    svc = getattr(bot, "enchant_service", None)
    if svc is None:
        from service.cache import EnchantCache
        from service.enchant_service import EnchantService

        cache = EnchantCache(ttl_sec=30)
        svc = EnchantService(cache)
    await bot.add_cog(EnchantCog(bot, svc))
