from __future__ import annotations
import discord

from constants import Language, Category
from msg_utils import MessageResolver
from user_data import get_user_language, update_user_data

from logger import logger

class LangService:
    def __init__(self):
        self.lang_map = {
            "zh": Language.ZH,
            "en": Language.EN,
            "jp": Language.JP,
        }

    async def change_language(self, task_num: str, guild_id: int, user_id: int, lang_code: str | None):
        """
        - lang_code=None → show current language
        - lang_code invalid → invalid message
        - lang_code valid → update language
        """
        user_lang = await get_user_language(guild_id, user_id)
        resolver = MessageResolver(guild_id, user_id)
        logger.debug(f"[{task_num}]Got current language.")

        if lang_code is None:
            logger.debug(f"[{task_num}]Show current language.")
            title = await resolver.get(Category.LANG, "current", lang_code=user_lang)
            return discord.Embed(title=title, color=discord.Color.blue())

        lang_code = lang_code.lower()
        if lang_code not in self.lang_map:
            logger.debug(f"[{task_num}]Invalid input.(not in lang code list)")
            title = await resolver.get(Category.LANG, "invalid")
            return discord.Embed(title=title, color=discord.Color.red())

        await update_user_data(
            guild_id,
            user_id,
            {"language": self.lang_map[lang_code].value},
        )
        logger.debug(f"[{task_num}]Language changed.")

        title = await resolver.get(Category.LANG, "updated", lang_code=lang_code)
        return discord.Embed(title=title, color=discord.Color.green())
