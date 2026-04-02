from typing import List, Dict
import random
from user_data import (
    get_user_data, update_user_data,
    get_seasonal_data, get_total_data,
)
from service.arena_rules import (
    Fighter,
    reverse_index,
    phase_meisterdieb,
    phase_rerolls,
    phase_mirrored,
    phase_add_sub,
    phase_multiply,
    extract_financial_flags,
    effective_len,
)
from logger import logger

# bet range
MIN_WAGER = 500
MAX_WAGER = 5000


async def _build_fighters(guild_id: int, participants_ids: List[int], name_map: Dict[int, str]) -> List[Fighter]:
    fighters: List[Fighter] = []
    for uid in participants_ids:
        ud = await get_user_data(guild_id, uid)
        fighters.append(
            Fighter(
                user_id=uid,
                name=name_map.get(uid, str(uid)),
                affix_ids=ud.get("affixes", []),
                affix_vals=ud.get("affix_values", []),
                is_corrupted=ud.get("is_corrupted", False),
            )
        )
    return fighters


async def _apply_settlement(
    guild_id: int,
    fighters: List[Fighter],
    wager: int
) -> None:
    # ranking
    fighters.sort(key=lambda x: effective_len(x), reverse=True)
    top_value = effective_len(fighters[0])
    bottom_value = effective_len(fighters[-1])
    winners = [f for f in fighters if effective_len(f) == top_value]
    losers  = [f for f in fighters if effective_len(f) == bottom_value]
    middle  = [f for f in fighters if f not in winners and f not in losers]

    updates: Dict[int, Dict] = {}

    # winner
    for f in winners:
        ud = await get_user_data(guild_id, f.user_id)
        gain = int(wager * (100 + f.financial_pct) / 100)
        ud["currency"] = max(0, int(ud.get("currency", 0)) + gain)
        updates.setdefault(f.user_id, {})["currency"] = ud["currency"]

        sd = await get_seasonal_data(guild_id, f.user_id)
        sd.arena_playcount += 1
        sd.win_count += 1
        updates[f.user_id]["data_seasonal"] = sd.to_dict()

        td = await get_total_data(guild_id, f.user_id)
        td.total_arena_count += 1
        td.total_win_count += 1
        updates[f.user_id]["data_total"] = td.to_dict()

    # loser
    for f in losers:
        ud = await get_user_data(guild_id, f.user_id)
        lose_amt = int(wager * f.scavenge_pct / 100)
        ud["currency"] = max(0, int(ud.get("currency", 0)) - lose_amt)
        updates.setdefault(f.user_id, {})["currency"] = ud["currency"]

        sd = await get_seasonal_data(guild_id, f.user_id)
        sd.arena_playcount += 1
        updates[f.user_id]["data_seasonal"] = sd.to_dict()

        td = await get_total_data(guild_id, f.user_id)
        td.total_arena_count += 1
        updates[f.user_id]["data_total"] = td.to_dict()

    # other
    for f in middle:
        sd = await get_seasonal_data(guild_id, f.user_id)
        sd.arena_playcount += 1

        td = await get_total_data(guild_id, f.user_id)
        td.total_arena_count += 1

        updates.setdefault(f.user_id, {})
        updates[f.user_id]["data_seasonal"] = sd.to_dict()
        updates[f.user_id]["data_total"] = td.to_dict()

    # write data
    for uid, data in updates.items():
        await update_user_data(guild_id, uid, data)


async def run_arena(
    task_num: str,
    guild_id: int,
    participants_ids: List[int],
    name_map: Dict[int, str],
    wager: int,
) -> Dict[str, List[Fighter]]:
    # Build Fighters
    try:
        fighters = await _build_fighters(guild_id, participants_ids, name_map)
        rev_index = reverse_index()
        logger.debug(f"[{task_num}]Arena created.")

        # 1) roll
        for f in fighters:
            f.base = random.randint(0, 20)
            f.final = f.base

        # (1) Meisterdieb
        phase_meisterdieb(fighters, rev_index, stage="initial")
        logger.debug(f"[{task_num}]Phase meisterdieb(base value) done.")

        # (2) reroll
        phase_rerolls(fighters, rev_index)
        logger.debug(f"[{task_num}]Phase reroll done.")

        # (2.5) Mirrored
        phase_mirrored(fighters, rev_index)
        logger.debug(f"[{task_num}]Phase mirrored done.")

        # (3) add/sub
        phase_add_sub(fighters, rev_index)
        logger.debug(f"[{task_num}]Phase add/sub done.")

        # (4) multiply
        phase_multiply(fighters, rev_index)
        logger.debug(f"[{task_num}]Phase multiply done.")

        # (5) Meisterdieb
        phase_meisterdieb(fighters, rev_index, stage="final")
        logger.debug(f"[{task_num}]Phase meisterdieb(final value) done.")

        # financial
        for f in fighters:
            extract_financial_flags(f, rev_index)

        # result
        await _apply_settlement(guild_id, fighters, wager)
        logger.debug(f"[{task_num}]Settlement done.")

        # winners/losers for UI
        fighters.sort(key=lambda x: effective_len(x), reverse=True)
        top_value = effective_len(fighters[0])
        bottom_value = effective_len(fighters[-1])
        winners = [f for f in fighters if effective_len(f) == top_value]
        losers  = [f for f in fighters if effective_len(f) == bottom_value]
        logger.info(f"[{task_num}]Arena finished. Winners={winners}, Losers={losers}")
    except Exception:
        logger.exception(f"[{task_num}]!!! Crashed !!!")
        raise

    return {
        "fighters": fighters,
        "winners": winners,
        "losers": losers,
    }
