from __future__ import annotations
from dataclasses import dataclass
from enum import Enum, auto
from typing import List, Optional
import discord
from service.cache import EnchantCache, UserState
from msg_utils import MessageResolver, Category, SubCategory, format_wager
from bank import safe_pay
from constants import Cost
from user_data import (
    get_user_data,
    update_user_data,
    set_write_fields,
    get_user_language
)
from service.enchant_rules import (
    load_enchantments,
    generate_random_affix_data,
    vaal_enchant,
    get_user_affixes_text,
)
from logger import logger


class EnchantOutcome(Enum):
    SUCCESS = auto()
    INSUFFICIENT = auto()
    ERROR = auto()

@dataclass
class EnchantPayload:
    """ViewModel for cog"""
    outcome: EnchantOutcome
    title: str
    description: str
    color_hint: Optional[int] = None
    current: Optional[int] = None
    affix_ids: Optional[List[int]] = None
    affix_values: Optional[List[int]] = None
    is_corrupted: Optional[bool] = None

class EnchantService:
    # ---------- get cache ----------
    def __init__(self, cache: EnchantCache):
        self.cache = cache
        load_enchantments()

    async def get_snapshot(self, guild_id: int, user_id: int):
        ce = await self.cache.get(guild_id, user_id)
        if ce is None:
            st = await self._load_state(guild_id, user_id)
            return {
                "currency": st.currency,
                "affixes": st.affixes[:],
                "affix_values": st.affix_values[:],
                "is_corrupted": st.is_corrupted,
            }
        st = ce.state
        return {
            "currency": st.currency,
            "affixes": st.affixes[:],
            "affix_values": st.affix_values[:],
            "is_corrupted": st.is_corrupted,
        }

    # ---------- read / write ----------
    async def _load_state(self, guild_id: int, user_id: int) -> UserState:
        ce = await self.cache.get(guild_id, user_id)
        if ce:
            return ce.state
        doc = await get_user_data(guild_id, user_id)
        st = UserState(
            currency=int(doc.get("currency", 0)),
            affixes=list(doc.get("affixes", [])),
            affix_values=list(doc.get("affix_values", [])),
            is_corrupted=bool(doc.get("is_corrupted", False)),
            update_time=doc.get("_update_time") if "_update_time" in doc else None,
        )
        await self.cache.put(guild_id, user_id, st, dirty=False)
        return st

    async def _write_back(self, guild_id: int, user_id: int, st: UserState):
        payload = {
            "currency": st.currency,
            "affixes": st.affixes,
            "affix_values": st.affix_values,
            "is_corrupted": st.is_corrupted,
        }
        data = set_write_fields(payload, ["currency", "affixes", "affix_values", "is_corrupted"])
        await update_user_data(guild_id, user_id, data)

    async def flush_user(self, guild_id: int, user_id: int):
        ce = await self.cache.get(guild_id, user_id)
        if not ce or not ce.dirty:
            return
        async with ce.lock:
            if not ce.dirty:
                return
            await self._write_back(guild_id, user_id, ce.state)
            ce.dirty = False

    async def flush_due(self):
        for key, ce in (await self.cache.due_entries()).items():
            gid, uid = map(int, key.split(":"))
            async with ce.lock:
                if ce.dirty:
                    await self._write_back(gid, uid, ce.state)
                    ce.dirty = False

    # ---------- job: show / roll / vaal ----------
    async def show_status(self, task_num: str, guild_id: int, user_id: int) -> EnchantPayload:
        try:
            st = await self._load_state(guild_id, user_id)
            logger.debug(f"[{task_num}]User data get")

            resolver = MessageResolver(guild_id, user_id)
            lang = await get_user_language(guild_id, user_id)

            title = await resolver.get(Category.STATUS, "enchantment")
            desc  = get_user_affixes_text(st.affixes, st.affix_values, lang=lang, is_corrupted=st.is_corrupted)
            logger.debug(f"[{task_num}]Affixes text created.")

            return EnchantPayload(
                outcome=EnchantOutcome.SUCCESS,
                title=title,
                description=desc,
                color_hint=discord.Color.blurple().value,
                current=st.currency,
                affix_ids=st.affixes,
                affix_values=st.affix_values,
                is_corrupted=st.is_corrupted
            )
        except Exception:
            logger.exception(f"[{task_num}]!!! Crashed !!!")
            raise

    # get new enchantment
    async def roll(self, task_num: str, guild_id: int, user_id: int) -> EnchantPayload:
        try:
            resolver = MessageResolver(guild_id, user_id)
            ce = await self.cache.get(guild_id, user_id)
            if ce is None:
                st = await self._load_state(guild_id, user_id)
                ce = await self.cache.put(guild_id, user_id, st)
            logger.debug(f"[{task_num}]User data get")

            async with ce.lock:
                # ----------------- payment ----------------
                ok, current = await safe_pay(guild_id, user_id, Cost.ENCHANT)
                if not ok:
                    logger.debug(f"[{task_num}]Payment failed.(Mochin)")
                    title = await resolver.get(Category.ENCHANT, SubCategory.TITLE, "not_enough_money")
                    desc  = await resolver.get(Category.ENCHANT, SubCategory.DESCRIPTION, "not_enough_money",
                                            amount=format_wager(Cost.ENCHANT), current=format_wager(current))
                    return EnchantPayload(EnchantOutcome.INSUFFICIENT, title, desc, discord.Color.red().value, current)
                logger.debug(f"[{task_num}]Payment success.")

                affix_ids, affix_values, is_corrupted = generate_random_affix_data()
                logger.debug(f"[{task_num}]Enchant done.")

                # ------ write to cache --------
                ce.state.currency = current
                ce.state.affixes = affix_ids
                ce.state.affix_values = affix_values
                ce.state.is_corrupted = is_corrupted
                ce.dirty = True
                logger.debug(f"[{task_num}]Wrote to cache.")

                lang = await get_user_language(guild_id, user_id)
                title = await resolver.get(Category.ENCHANT, SubCategory.TITLE, "success")
                desc  = await resolver.get(Category.ENCHANT, SubCategory.DESCRIPTION, "success", current=format_wager(current))
                desc += get_user_affixes_text(affix_ids, affix_values, lang=lang, is_corrupted=is_corrupted)
                logger.debug(f"[{task_num}]Affixes text created.")

                return EnchantPayload(
                    outcome=EnchantOutcome.SUCCESS,
                    title=title,
                    description=desc,
                    color_hint=discord.Color.blue().value,
                    current=current,
                    affix_ids=affix_ids,
                    affix_values=affix_values,
                    is_corrupted=is_corrupted
                )
        except Exception:
            logger.exception(f"[{task_num}]!!! Crashed !!!")
            raise
    
    async def vaal(self, task_num: str, guild_id: int, user_id: int) -> EnchantPayload:
        try:
            resolver = MessageResolver(guild_id, user_id)
            ce = await self.cache.get(guild_id, user_id)
            if ce is None:
                st = await self._load_state(guild_id, user_id)
                ce = await self.cache.put(guild_id, user_id, st)
            logger.debug(f"[{task_num}]User data get")

            async with ce.lock:
                # ------------- set corrupted --------------
                if ce.state.is_corrupted:
                    logger.debug(f"[{task_num}]Vaal failed.(Already corrupted)")
                    title = await resolver.get(Category.VAAL, SubCategory.TITLE, "already")
                    desc  = await resolver.get(Category.VAAL, SubCategory.DESCRIPTION, "already")
                    return EnchantPayload(
                        outcome=EnchantOutcome.ERROR, title=title, description=desc,
                        color_hint=discord.Color.red().value,
                        current=ce.state.currency, affix_ids=ce.state.affixes,
                        affix_values=ce.state.affix_values, is_corrupted=True
                    )
                
                
                # ------------- payment --------------
                ok, current = await safe_pay(guild_id, user_id, Cost.VAAL)
                if not ok:
                    logger.debug(f"[{task_num}]Vaal failed.(Mochin)")
                    title = await resolver.get(Category.VAAL, SubCategory.TITLE, "not_enough_money")
                    desc  = await resolver.get(Category.VAAL, SubCategory.DESCRIPTION, "not_enough_money",
                                            amount=format_wager(Cost.VAAL), current=format_wager(current))
                    return EnchantPayload(EnchantOutcome.INSUFFICIENT, title, desc, discord.Color.red().value, current)

                # update cache
                user_like = {
                    "affixes": ce.state.affixes[:],
                    "affix_values": ce.state.affix_values[:],
                    "is_corrupted": ce.state.is_corrupted,
                }
                
                affix_ids, affix_values, is_corrupted = vaal_enchant(user_like)
                logger.debug(f"[{task_num}]Vaal done.")

                ce.state.currency = current
                ce.state.affixes = affix_ids
                ce.state.affix_values = affix_values
                ce.state.is_corrupted = is_corrupted
                ce.dirty = True

                lang = await get_user_language(guild_id, user_id)

                title = await resolver.get(Category.VAAL, SubCategory.TITLE, "success")
                desc  = await resolver.get(Category.VAAL, SubCategory.DESCRIPTION, "success", current=format_wager(current))
                desc += get_user_affixes_text(affix_ids, affix_values, lang=lang, is_corrupted=is_corrupted)
                logger.debug(f"[{task_num}]Affixes text created.")

                return EnchantPayload(
                    outcome=EnchantOutcome.SUCCESS, title=title, description=desc,
                    color_hint=discord.Color.purple().value,
                    current=current, affix_ids=affix_ids, affix_values=affix_values, is_corrupted=is_corrupted
                )
        except Exception:
            logger.exception(f"[{task_num}]!!! Crashed !!!")
            raise


