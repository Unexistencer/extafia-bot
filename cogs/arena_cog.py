import asyncio
import random
from typing import Dict, List

import discord
from discord import app_commands
from discord.ext import commands

from msg_utils import MessageResolver, PagedView, format_wager
from constants import Category
from service.arena_service import MAX_WAGER, MIN_WAGER, run_arena
from service.arena_rules import Fighter, effective_len, render_cock_display

from logger import logger, generate_task_num

# ─────────────────────── Embed length protection ───────────────────────────────
MAX_EMBED_TOTAL = 6000
MAX_DESC = 3900
SAFE_FIELD = 980
JOIN_EMOJI = "✅"


def _clamp_text(text: str, limit: int) -> str:
    text = text or ""
    return text if len(text) <= limit else text[: max(0, limit - 1)] + "…"


def _clamp_lines(lines: List[str], limit_chars: int) -> str:
    out: List[str] = []
    used = 0
    for line in lines:
        line = line.rstrip()
        needed = len(line) + 1
        if used + needed > limit_chars:
            out.append(f"… and {len(lines) - len(out)} more")
            break
        out.append(line)
        used += needed
    return "\n".join(out)


def _sanitize_embed(embed: discord.Embed) -> discord.Embed:
    # clamp desc
    if embed.description:
        embed.description = _clamp_text(embed.description, MAX_DESC)

    # clamp each field value
    if getattr(embed, "fields", None):
        for field in embed.fields:
            if field.value:
                field.value = _clamp_text(str(field.value), SAFE_FIELD)

    # keep embed max length
    total = len(embed.title or "") + len(embed.description or "") + len(embed.footer.text or "")
    total += sum((len(field.name or "") + len(field.value or "")) for field in embed.fields)
    if total > MAX_EMBED_TOTAL and embed.description:
        shrink = min(len(embed.description), total - MAX_EMBED_TOTAL + 200)
        embed.description = _clamp_text(embed.description, max(500, len(embed.description) - shrink))
    return embed


# ─────────────────────── Create Arena ───────────────────────────────
class ArenaCog(commands.Cog, name="Arena"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="arena", description="Host a COCK ARENA")
    async def arena(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=False)
        await self._run_arena(
            task_num=generate_task_num(),
            guild=interaction.guild,
            host=interaction.user,
            send_message=lambda **kwargs: interaction.followup.send(**kwargs),
            fetch_message=lambda message_id: interaction.channel.fetch_message(message_id),
            owner_id=interaction.user.id,
        )

    @commands.command(name="arena")
    async def arena_prefix(self, ctx: commands.Context):
        async with ctx.typing():
            await self._run_arena(
                task_num=generate_task_num(),
                guild=ctx.guild,
                host=ctx.author,
                send_message=lambda **kwargs: ctx.send(**kwargs),
                fetch_message=lambda message_id: ctx.channel.fetch_message(message_id),
                owner_id=ctx.author.id,
            )

    async def _run_arena(self, task_num: str, guild: discord.Guild | None, host: discord.abc.User, send_message, fetch_message, owner_id: int):
        logger.info(
            f"[{task_num}]arena invoked by {host} #{host.id} "
            f"in guild {guild} #{guild.id if guild else 0}"
        )

        if guild is None:
            await send_message(content="This command can only be used in a server.")
            return

        guild_id = guild.id
        # locale
        resolver = MessageResolver(guild_id, host.id)
        title = await resolver.get(Category.ARENA, "host", "title", user=host.display_name)

        # bet amount
        wager = random.randint(MIN_WAGER, MAX_WAGER)
        desc = await resolver.get(Category.ARENA, "host", "description", amount=format_wager(wager))
        open_embed = discord.Embed(title=title, description=desc, color=discord.Color.orange())

        msg = await send_message(embed=open_embed)
        # add reaction
        try:
            await msg.add_reaction(JOIN_EMOJI)
        except discord.Forbidden:
            pass

        # wait-time
        logger.info(f"[{task_num}]Waiting players...")
        await asyncio.sleep(20)

        # timeout and fetch players
        try:
            final = await fetch_message(msg.id)
        except discord.NotFound:
            await send_message(content="Arena lobby message disappeared before the match started.")
            return

        reaction = discord.utils.get(final.reactions, emoji=JOIN_EMOJI)
        participants_ids = [host.id]
        if reaction:
            users = [user async for user in reaction.users()]
            participants_ids.extend([user.id for user in users if not user.bot and user.id != host.id])

        participants_ids = list(dict.fromkeys(participants_ids))
        # at least 2 players
        if len(participants_ids) < 2:
            logger.info(f"[{task_num}]Arena failed.(Not enough players)")
            fail_title = await resolver.get(Category.ARENA, "failed", "title")
            fail_desc = await resolver.get(Category.ARENA, "failed", "description")
            await send_message(
                embed=discord.Embed(title=fail_title, description=fail_desc, color=discord.Color.red())
                )
            return

        # name map
        name_map: Dict[int, str] = {}
        for user_id in participants_ids:
            member = guild.get_member(user_id)
            name_map[user_id] = member.display_name if member else str(user_id)

        # arena start
        logger.info(f"[{task_num}]Arena started.")
        result = await run_arena(
            task_num=task_num,
            guild_id=guild_id,
            participants_ids=participants_ids,
            name_map=name_map,
            wager=wager,
        )

        fighters: List[Fighter] = result["fighters"]
        winners: List[Fighter] = result["winners"]
        losers: List[Fighter] = result["losers"]

        # result
        fighters.sort(key=lambda fighter: effective_len(fighter), reverse=True)
        overview_lines: List[str] = []
        for fighter in fighters:
            cock = render_cock_display(fighter)
            overview_lines.append(f"<@{fighter.user_id}>\n`{cock}`")

        overview_desc = _clamp_lines(overview_lines, MAX_DESC)

        # winner/loser
        for winner in winners:
            gain = int(wager * (100 + winner.financial_pct) / 100)
            text = await resolver.get(Category.ARENA, "win", user=winner.name, amount=format_wager(gain))
            overview_desc += "\n" + text

        for loser in losers:
            lose_amt = int(wager * loser.scavenge_pct / 100)
            text = await resolver.get(Category.ARENA, "lose", user=loser.name, amount=format_wager(lose_amt))
            overview_desc += "\n" + text

        result_title = await resolver.get(Category.ARENA, "result")
        result_embed = _sanitize_embed(
            discord.Embed(title=result_title, description=overview_desc, color=discord.Color.brand_green())
        )

        view = BattleLogView(fighters, sanitize_embed_fn=_sanitize_embed, owner_id=owner_id)
        logger.info(f"[{task_num}]Embed done.")
        await send_message(embed=result_embed, view=view)


# ─────────────────────── Battle Log View ───────────────────────────────
class BattleLogView(discord.ui.View):
    def __init__(self, fighters: List[Fighter], owner_id: int, sanitize_embed_fn=None, timeout: int = 180):
        super().__init__(timeout=timeout)
        self.fighters = fighters
        self.owner_id = owner_id
        self._sanitize = sanitize_embed_fn

    async def _localize_log_lines(self, lines: List[str], resolver: MessageResolver) -> List[str]:
        tag_map = {
            "[Prefix]": await resolver.get(Category.ARENA, "battle_log", "prefix"),
            "[Suffix]": await resolver.get(Category.ARENA, "battle_log", "suffix"),
            "[Debuff]": await resolver.get(Category.ARENA, "battle_log", "debuff"),
            "[Bonus]": await resolver.get(Category.ARENA, "battle_log", "bonus"),
        }
        out: List[str] = []
        for line in lines or ["No battle log available."]:
            for key, value in tag_map.items():
                if key in line:
                    line = line.replace(key, f"[{value}]")
            out.append(line)
        return out

    async def _build_log_embeds(self, guild_id: int, user_id: int) -> List[discord.Embed]:
        resolver = MessageResolver(guild_id, user_id)
        embeds: List[discord.Embed] = []
        for fighter in self.fighters:
            # locale
            loc_lines = await self._localize_log_lines(fighter.log, resolver)
            log_text = "\n".join(loc_lines)
            # cut size if text over size
            log_text = log_text if len(log_text) <= 1800 else log_text[:1799] + "…"

            title = await resolver.get(Category.ARENA, "battle_log", "title", name=fighter.name)
            eff = effective_len(fighter)
            field_shape = await resolver.get(Category.ARENA, "battle_log", "shape", len=eff)
            cock = render_cock_display(fighter)

            embed = discord.Embed(title=title, description=log_text, color=discord.Color.blurple())
            embed.add_field(name=field_shape, value=f"`{cock}`", inline=False)
            if self._sanitize:
                embed = self._sanitize(embed)
            embeds.append(embed)
        return embeds

    @discord.ui.button(label="Battle Log", style=discord.ButtonStyle.secondary)
    async def open_logs(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild_id = interaction.guild.id
        user_id = interaction.user.id
        log_embeds = await self._build_log_embeds(guild_id, user_id)
        if not log_embeds:
            await interaction.response.send_message("No battle log available.", ephemeral=True)
            return
        pv = PagedView(log_embeds, owner_id=self.owner_id, timeout=180)
        await interaction.response.send_message(embed=log_embeds[0], view=pv, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(ArenaCog(bot))
