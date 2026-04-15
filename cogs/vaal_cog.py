from __future__ import annotations

import discord
from discord.ext import commands, tasks
from discord import app_commands, Interaction

from service.enchant_service import EnchantService, EnchantPayload

from logger import logger, generate_task_num


class VaalCog(commands.Cog):
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

    @app_commands.command(name="vaal", description="Corrupt your cock")
    async def vaal(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)
        await self._run_vaal(
            task_num=generate_task_num(),
            guild_id=interaction.guild.id if interaction.guild else 0,
            user_id=interaction.user.id,
            actor=str(interaction.user),
            guild=str(interaction.guild),
            send_result=lambda embed, view: interaction.edit_original_response(embed=embed, view=view),
        )

    @commands.command(name="vaal")
    async def vaal_prefix(self, ctx: commands.Context):
        async with ctx.typing():
            await self._run_vaal(
                task_num=generate_task_num(),
                guild_id=ctx.guild.id if ctx.guild else 0,
                user_id=ctx.author.id,
                actor=str(ctx.author),
                guild=str(ctx.guild),
                send_result=lambda embed, view: ctx.send(embed=embed, view=view),
            )

    async def _run_vaal(self, task_num: str, guild_id: int, user_id: int, actor: str, guild: str, send_result):
        logger.info(
            f"[{task_num}]vaal invoked by {actor} #{user_id} "
            f"in guild {guild} #{guild_id}"
        )
        await self.svc.flush_user(guild_id, user_id)

        payload = await self.svc.vaal(task_num, guild_id, user_id)

        embed = self._to_embed(payload)
        view = VaalView(self.svc, guild_id, user_id, self._to_embed)
        logger.info(f"[{task_num}]Embed done.")
        await send_result(embed, view)

    def _to_embed(self, p: EnchantPayload) -> discord.Embed:
        color = p.color_hint if p.color_hint is not None else discord.Color.greyple().value
        return discord.Embed(title=p.title, description=p.description, color=color)


class VaalView(discord.ui.View):
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


async def setup(bot: commands.Bot):
    svc = getattr(bot, "enchant_service", None)
    if svc is None:
        from service.cache import EnchantCache
        from service.enchant_service import EnchantService

        cache = EnchantCache(ttl_sec=30)
        svc = EnchantService(cache)
    await bot.add_cog(VaalCog(bot, svc))
