import json
from typing import Any, List, Optional, Iterable, Set
import discord
from discord.ui import View, Button
from constants import *
from user_data import *
from enum import Enum

# read json
with open("data/message.json", "r", encoding="utf-8") as f:
    messages = json.load(f)

class MessageResolver:
    def __init__(self, guild_id: int, user_id: int):
        self.guild_id = guild_id
        self.user_id = user_id

    async def get(self, *keys: Any, **kwargs) -> str:
        user_lang = await get_user_language(self.guild_id, self.user_id)

        lang_data = messages.get(user_lang, messages["en"])
        keys = [k.value if isinstance(k, Enum) else k for k in keys]

        message = lang_data
        for key in keys:
            if isinstance(message, dict):
                message = message.get(key)
            else:
                break

        if message is None:
            return f"Missing translation: {'.'.join(str(k) for k in keys)}"

        if isinstance(message, str):
            return message.format(**kwargs)
        return message


class PagedView(View):
    def __init__(
        self,
        embeds: List[discord.Embed],
        owner_id: Optional[int] = None,
        allowed_user_ids: Optional[Iterable[int]] = None,
        forbidden_message: str = "403 Forbidden: You don't have permission to operate this page.",
        timeout: int = 180
    ):
        super().__init__(timeout=timeout)
        self.embeds = embeds
        self.idx = 0
        self.owner_id = owner_id
        self.allowed_user_ids: Optional[Set[int]] = set(allowed_user_ids) if allowed_user_ids else None
        self.forbidden_message = forbidden_message
        self.message: Optional[discord.Message] = None  # on_timeout

    async def on_timeout(self):
        for c in self.children:
            if isinstance(c, Button):
                c.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass

    def _permitted(self, user: Optional[discord.User]) -> bool:
        if user is None:
            return False
        if self.owner_id is not None:
            return user.id == self.owner_id
        if self.allowed_user_ids is not None:
            return user.id in self.allowed_user_ids
        return True

    async def _guard(self, interaction: discord.Interaction) -> bool:
        if not self._permitted(interaction.user):
            try:
                await interaction.response.send_message(self.forbidden_message, ephemeral=True)
            except Exception:
                pass
            return False
        return True

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
    async def prev(self, interaction: discord.Interaction, button: Button):
        if not await self._guard(interaction): return
        if not self.embeds: return
        self.idx = (self.idx - 1) % len(self.embeds)
        await interaction.response.edit_message(embed=self.embeds[self.idx], view=self)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: Button):
        if not await self._guard(interaction): return
        if not self.embeds: return
        self.idx = (self.idx + 1) % len(self.embeds)
        await interaction.response.edit_message(embed=self.embeds[self.idx], view=self)

class ToggleView(View):
    def __init__(
        self,
        result_embed: discord.Embed,
        choices_embed: discord.Embed,
        owner_id: Optional[int] = None,
        allowed_user_ids: Optional[Iterable[int]] = None,
        options_label: str = "Options",
        result_label: str = "Result",
        forbidden_message: str = "403 Forbidden: You don't have permission to operate this page.",
        timeout: int = 180
    ):
        super().__init__(timeout=timeout)
        self.result_embed = result_embed
        self.choices_embed = choices_embed
        self.owner_id = owner_id
        self.allowed_user_ids: Optional[Set[int]] = set(allowed_user_ids) if allowed_user_ids else None
        self.options_label = options_label
        self.result_label = result_label
        self.forbidden_message = forbidden_message
        self.message: Optional[discord.Message] = None
        self.showing_result = True
        self.toggle.label = self.options_label

    async def on_timeout(self):
        for c in self.children:
            if isinstance(c, Button):
                c.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass

    def _permitted(self, user: Optional[discord.User]) -> bool:
        if user is None:
            return False
        if self.owner_id is not None:
            return user.id == self.owner_id
        if self.allowed_user_ids is not None:
            return user.id in self.allowed_user_ids
        return True

    async def _guard(self, interaction: discord.Interaction) -> bool:
        if not self._permitted(interaction.user):
            try:
                await interaction.response.send_message(self.forbidden_message, ephemeral=True)
            except Exception:
                pass
            return False
        return True

    @discord.ui.button(label="Options", style=discord.ButtonStyle.secondary)
    async def toggle(self, interaction: discord.Interaction, button: Button):
        if not await self._guard(interaction):
            return

        self.showing_result = not self.showing_result
        if self.showing_result:
            button.label = self.options_label
            embed = self.result_embed
        else:
            button.label = self.result_label
            embed = self.choices_embed

        await interaction.response.edit_message(embed=embed, view=self)


def format_wager(wager_amount):
    wager = ""
    gold = wager_amount//10000
    silver = (wager_amount-gold*10000)//100
    bronze = wager_amount-gold*10000-silver*100

    if gold != 0:
        wager += str(gold) + "<:shingcoin_1:952960803663937577> "
    if silver != 0:
        wager += str(silver) + "<:shingcoin_2:952962920940200026> "
    if bronze != 0:
        wager += str(bronze) + "<:shingcoin_3:952963842248421466>"
    return wager
