from __future__ import annotations
import discord
from constants import *
from user_data import get_user_data, get_seasonal_data, get_total_data
from service.enchant_rules import get_user_affixes_text
from msg_utils import MessageResolver, format_wager
from logger import logger

class StatusService:
    async def build_status_embeds(self, task_num: str, guild_id: int, user_id: int, display_name: str) -> list[discord.Embed]:
        try:
            user_data = await get_user_data(guild_id, user_id)
            resolver = MessageResolver(guild_id, user_id)
            lang = user_data.get("language", Language.EN.value)

            sd = await get_seasonal_data(guild_id, user_id)
            td = await get_total_data(guild_id, user_id)

            title_text = await resolver.get(Category.STATUS, "title", name=display_name)

            embeds: list[discord.Embed] = []

            # Page1: Currency and Arena record
            embed1 = discord.Embed(title=title_text, color=discord.Color.green())
            currency_name = await resolver.get(Category.STATUS, "currency")
            seasonal_name = await resolver.get(Category.STATUS, "data_seasonal")
            total_name = await resolver.get(Category.STATUS, "data_total")
            logger.debug(f"[{task_num}]Page1 data got.")
            
            # Currency
            embed1.add_field(
                name=currency_name,
                value=format_wager(user_data.get("currency", 0)),
                inline=False,
            )

            # Seasonal block
            participation_txt = await resolver.get(
                Category.STATUS, "participation", value=sd.arena_playcount
            )
            win_txt = await resolver.get(
                Category.STATUS, "win", value=sd.win_count
            )
            eightD_txt = await resolver.get(
                Category.STATUS, "8D", value=sd.eightD_count
            )
            longest_txt = await resolver.get(
                Category.STATUS, "longest", value=sd.longest
            )
            embed1.add_field(
                name=seasonal_name,
                value="\n".join([participation_txt, win_txt, eightD_txt, longest_txt]),
                inline=False,
            )
            logger.debug(f"[{task_num}]Seasonal data marked.")

            # Total block
            total_participation_txt = await resolver.get(
                Category.STATUS, "participation", value=td.total_arena_count
            )
            total_win_txt = await resolver.get(
                Category.STATUS, "win", value=td.total_win_count
            )
            total_8D_txt = await resolver.get(
                Category.STATUS, "8D", value=td.total_8D_count
            )
            total_longest_txt = await resolver.get(
                Category.STATUS, "longest", value=td.total_longest
            )
            embed1.add_field(
                name=total_name,
                value="\n".join(
                    [
                        total_participation_txt,
                        total_win_txt,
                        total_8D_txt,
                        total_longest_txt,
                    ]
                ),
                inline=False,
            )
            logger.debug(f"[{task_num}]Total data marked.")

            embeds.append(embed1)
            logger.debug(f"[{task_num}]Page1 done.")

            # Page2: Enchantment
            embed2 = discord.Embed(title=title_text, color=discord.Color.dark_purple())

            enchantment_txt = await resolver.get(Category.STATUS, "enchantment")

            affix_ids = user_data.get("affixes", [])
            affix_values = user_data.get("affix_values", [])
            is_corrupted = user_data.get("is_corrupted", False)
            logger.debug(f"[{task_num}]Page2 data got.")

            embed2.add_field(
                name=enchantment_txt,
                value=get_user_affixes_text(
                    affix_ids,
                    affix_values,
                    lang=lang,
                    is_corrupted=is_corrupted,
                ),
                inline=False,
            )
            logger.debug(f"[{task_num}]Enchantments marked.")

            embeds.append(embed2)
            logger.debug(f"[{task_num}]Page2 done.")

            # Page3: Achievements (WIP)
            embed3 = discord.Embed(title=title_text, color=discord.Color.gold())
            achievement_txt = await resolver.get(Category.STATUS, "achievement")
            logger.debug(f"[{task_num}]Page3 data got.")

            embed3.add_field(name=achievement_txt, value="WIP", inline=False)
            logger.debug(f"[{task_num}]Achievements marked.")

            embeds.append(embed3)
            logger.debug(f"[{task_num}]Page3 done.")
        except Exception:
            logger.exception(f"[{task_num}]!!! Crashed !!!")
            raise

        return embeds
