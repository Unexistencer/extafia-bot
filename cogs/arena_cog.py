import asyncio
import random
from typing import List, Dict

import discord
from discord import app_commands
from discord.ext import commands

from msg_utils import MessageResolver, PagedView, format_wager
from constants import Category
from service.arena_service import run_arena, MIN_WAGER, MAX_WAGER
from service.arena_rules import Fighter, effective_len, render_cock_display

from logger import logger, generate_task_num

# ─────────────────────── Embed length protection ───────────────────────────────
MAX_EMBED_TOTAL = 6000
MAX_DESC = 3900
MAX_FIELD = 1024
SAFE_FIELD = 980
JOIN_EMOJI = "✅"

def _clamp_text(s: str, limit: int) -> str:
    s = s or ""
    return s if len(s) <= limit else s[: max(0, limit - 1)] + "…"

def _clamp_lines(lines, limit_chars) -> str:
    out, used = [], 0
    for ln in lines:
        ln = ln.rstrip()
        need = len(ln) + 1
        if used + need > limit_chars:
            out.append(f"…（還有 {len(lines) - len(out)} 行）")
            break
        out.append(ln); used += need
    return "\n".join(out)

def _sanitize_embed(e: discord.Embed) -> discord.Embed:
    # clamp desc
    if e.description:
        e.description = _clamp_text(e.description, MAX_DESC)
    # clamp each field value
    if getattr(e, "fields", None):
        for f in e.fields:
            if f.value:
                f.value = _clamp_text(str(f.value), SAFE_FIELD)
    # keep embed max length
    total = len(e.title or "") + len(e.description or "") + len(e.footer.text or "")
    total += sum((len(f.name or "") + len(f.value or "")) for f in e.fields)
    if total > MAX_EMBED_TOTAL and e.description:
        shrink = min(len(e.description), total - MAX_EMBED_TOTAL + 200)
        e.description = _clamp_text(e.description, max(500, len(e.description) - shrink))
    return e

# ─────────────────────── Create Arena ───────────────────────────────
class ArenaCog(commands.Cog, name="Arena"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="arena", description="Host a COCK ARENA")
    
    async def arena(self, interaction: discord.Interaction):
        task_num = generate_task_num()
        logger.info(
            f"[{task_num}]arena invoked by {interaction.user} #{interaction.user.id} "
            f"in guild {interaction.guild} #{interaction.guild.id}"
            )
        
        guild = interaction.guild
        host  = interaction.user
        guild_id = guild.id
        
        await interaction.response.defer(thinking=True, ephemeral=False)        

        # locale
        resolver = MessageResolver(guild_id, host.id)
        title = await resolver.get(Category.ARENA, "host", "title", user=host.display_name)

        # bet amount
        wager = random.randint(MIN_WAGER, MAX_WAGER)

        desc = await resolver.get(Category.ARENA, "host", "description", amount=format_wager(wager))
        open_embed = discord.Embed(title=title, description=desc, color=discord.Color.orange())

        msg = await interaction.followup.send(embed=open_embed)
        
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
            final = await interaction.channel.fetch_message(msg.id)
        except discord.NotFound:
            await interaction.followup.send("訊息已不存在，無法開賽。")
            return

        reaction = discord.utils.get(final.reactions, emoji=JOIN_EMOJI)
        participants_ids = [host.id]
        if reaction:
            users = [u async for u in reaction.users()]
            participants_ids.extend([u.id for u in users if not u.bot and u.id != host.id])

        participants_ids = list(dict.fromkeys(participants_ids))

        # at least 2 players
        if len(participants_ids) < 2:
            logger.info(f"[{task_num}]Arena failed.(Not enough players)")
            fail_title = await resolver.get(Category.ARENA, "failed", "title")
            fail_desc = await resolver.get(Category.ARENA, "failed", "description")
            await interaction.followup.send(
                embed=discord.Embed(title=fail_title, description=fail_desc, color=discord.Color.red())
            )
            return

        # name map
        name_map: Dict[int, str] = {}
        for uid in participants_ids:
            m = guild.get_member(uid)
            name_map[uid] = m.display_name if m else str(uid)

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
        winners: List[Fighter]  = result["winners"]
        losers:  List[Fighter]  = result["losers"]

        # result
        fighters.sort(key=lambda x: effective_len(x), reverse=True)
        overview_lines = []
        for f in fighters:
            cock = render_cock_display(f)
            overview_lines.append(f"<@{f.user_id}>\n`{cock}`")

        overview_desc = _clamp_lines(overview_lines, MAX_DESC)

        # winner/loser
        for w in winners:
            gain = int(wager * (100 + w.financial_pct) / 100)
            text = await resolver.get(Category.ARENA, "win", user=w.name, amount=format_wager(gain))
            overview_desc += "\n" + text

        for l in losers:
            lose_amt = int(wager * l.scavenge_pct / 100)
            text = await resolver.get(Category.ARENA, "lose", user=l.name, amount=format_wager(lose_amt))
            overview_desc += "\n" + text

        result_title = await resolver.get(Category.ARENA, "result")
        result_embed = _sanitize_embed(
            discord.Embed(title=result_title, description=overview_desc, color=discord.Color.brand_green())
        )

        view = BattleLogView(fighters, sanitize_embed_fn=_sanitize_embed)
        logger.info(f"[{task_num}]Embed done.")
        await interaction.followup.send(embed=result_embed, view=view)



# ─────────────────────── Battle Log View ───────────────────────────────
class BattleLogView(discord.ui.View):
    def __init__(self, fighters: List[Fighter], sanitize_embed_fn=None, timeout: int = 180):
        super().__init__(timeout=timeout)
        self.fighters = fighters
        self._sanitize = sanitize_embed_fn

    async def _localize_log_lines(self, lines: List[str], resolver: MessageResolver) -> List[str]:
        tag_map = {
            "[Prefix]":  await resolver.get(Category.ARENA, "battle_log", "prefix"),
            "[Suffix]":  await resolver.get(Category.ARENA, "battle_log", "suffix"),
            "[Debuff]":  await resolver.get(Category.ARENA, "battle_log", "debuff"),
            "[Bonus]":   await resolver.get(Category.ARENA, "battle_log", "bonus"),
        }
        out = []
        for ln in lines or ["（無記錄）"]:
            for k, v in tag_map.items():
                if k in ln:
                    ln = ln.replace(k, f"[{v}]")
            out.append(ln)
        return out

    async def _build_log_embeds(self, guild_id: int, user_id: int) -> List[discord.Embed]:
        resolver = MessageResolver(guild_id, user_id)
        embeds: List[discord.Embed] = []
        for f in self.fighters:
            # locale
            loc_lines = await self._localize_log_lines(f.log, resolver)
            log_text = "\n".join(loc_lines)
            # cut size if text over size
            log_text = log_text if len(log_text) <= 1800 else log_text[:1799] + "…"

            title = await resolver.get(Category.ARENA, "battle_log", "title", name=f.name)
            eff = effective_len(f)
            field_shape = await resolver.get(Category.ARENA, "battle_log", "shape", len=eff)
            cock = render_cock_display(f)

            e = discord.Embed(title=title, description=log_text, color=discord.Color.blurple())
            e.add_field(name=field_shape, value=f"`{cock}`", inline=False)
            if self._sanitize:
                e = self._sanitize(e)
            embeds.append(e)
        return embeds

    @discord.ui.button(label="Battle Log", style=discord.ButtonStyle.secondary)
    async def open_logs(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild_id = interaction.guild.id
        user_id  = interaction.user.id
        log_embeds = await self._build_log_embeds(guild_id, user_id)
        if not log_embeds:
            await interaction.response.send_message("沒有戰鬥記錄。", ephemeral=True)
            return
        pv = PagedView(log_embeds, owner_id=interaction.user.id, timeout=180)
        await interaction.response.send_message(embed=log_embeds[0], view=pv, ephemeral=True)




async def setup(bot: commands.Bot):
    await bot.add_cog(ArenaCog(bot))
