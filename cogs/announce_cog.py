import time
from typing import Dict, Tuple, Optional, List, Set

import discord
from discord.ext import commands
from discord import app_commands

from guild_data import (
    get_announce_channel,
    set_announce_channel,
    get_excluded_voice_channels,
    add_excluded_voice_channel,
    remove_excluded_voice_channel,
)

JoinKey = Tuple[int, int]      # (guild_id, user_id)
JoinValue = Tuple[int, float]  # (channel_id, join_time_monotonic)


class AnnounceCog(commands.GroupCog, name="announce"):
    """leave detect + announce channel"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._join_times: Dict[JoinKey, JoinValue] = {}
        self.threshold_seconds: float = 5.0

    # ========= Slash Commands =========

    @app_commands.command(name="set", description="set this text channel as announce channel")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def cmd_set(self, interaction: discord.Interaction):
        if not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message(
                "這個指令只能在文字頻道裡使用。", ephemeral=True
            )
            return

        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("無法取得伺服器資訊。", ephemeral=True)
            return

        await set_announce_channel(guild.id, interaction.channel.id)
        await interaction.response.send_message(
            f"已將 <#{interaction.channel.id}> 設為偷聽公告頻道。", ephemeral=False
        )

    @app_commands.command(name="unset", description="disable announce channel")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def cmd_unset(self, interaction: discord.Interaction):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("無法取得伺服器資訊。", ephemeral=True)
            return

        await set_announce_channel(guild.id, None)
        await interaction.response.send_message(
            "已關閉偷聽公告功能。", ephemeral=True
        )

    @app_commands.command(
        name="private_add",
        description="將指定語音頻道加入排除名單（不偵測偷聽）"
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def cmd_private_add(
        self,
        interaction: discord.Interaction,
        voice_channel: discord.VoiceChannel,
    ):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("無法取得伺服器資訊。", ephemeral=True)
            return

        await add_excluded_voice_channel(guild.id, voice_channel.id)
        await interaction.response.send_message(
            f"已將語音頻道 `{voice_channel.name}` 加入排除名單。", ephemeral=True
        )

    @app_commands.command(
        name="private_remove",
        description="從排除名單移除指定語音頻道"
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def cmd_private_remove(
        self,
        interaction: discord.Interaction,
        voice_channel: discord.VoiceChannel,
    ):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("無法取得伺服器資訊。", ephemeral=True)
            return

        await remove_excluded_voice_channel(guild.id, voice_channel.id)
        await interaction.response.send_message(
            f"已將語音頻道 `{voice_channel.name}` 從排除名單移除。", ephemeral=True
        )

    @app_commands.command(
        name="private_list",
        description="顯示目前排除的語音頻道列表"
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def cmd_private_list(self, interaction: discord.Interaction):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("無法取得伺服器資訊。", ephemeral=True)
            return

        excluded_ids: List[int] = await get_excluded_voice_channels(guild.id)
        if not excluded_ids:
            await interaction.response.send_message(
                "目前沒有任何語音頻道被排除。", ephemeral=True
            )
            return

        lines: List[str] = []
        for cid in excluded_ids:
            ch = guild.get_channel(cid)
            if isinstance(ch, discord.VoiceChannel):
                lines.append(f"- `{ch.name}` (ID: {cid})")
            else:
                lines.append(f"- (已不存在) ID: {cid}")

        text = "目前排除的語音頻道：\n" + "\n".join(lines)
        await interaction.response.send_message(text, ephemeral=True)

    # ========= listener =========

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        if member.bot:
            return

        guild = member.guild
        if guild is None:
            return

        announce_channel_id = await get_announce_channel(guild.id)
        if not announce_channel_id:
            return  # announce nth
        
        excluded_list = await get_excluded_voice_channels(guild.id)
        excluded_channels: Set[int] = set(excluded_list)

        now = time.monotonic()

        # Channel A -> B
        if before.channel is not None and after.channel is not None:
            if before.channel.id != after.channel.id:
                await self._handle_leave(
                    member,
                    before.channel,
                    announce_channel_id,
                    excluded_channels,
                    now,
                )
                self._handle_join(member, after.channel, excluded_channels, now)
            return

        # None -> Channel A
        if before.channel is None and after.channel is not None:
            self._handle_join(member, after.channel, excluded_channels, now)
            return

        # Channel A -> None
        if before.channel is not None and after.channel is None:
            await self._handle_leave(
                member,
                before.channel,
                announce_channel_id,
                excluded_channels,
                now,
            )
            return

    # ========= utils =========

    def _handle_join(
        self,
        member: discord.Member,
        channel: discord.VoiceChannel,
        excluded_channels: Set[int],
        now: float,
    ) -> None:
        if channel.id in excluded_channels:
            return

        key: JoinKey = (member.guild.id, member.id)
        self._join_times[key] = (channel.id, now)

    async def _handle_leave(
        self,
        member: discord.Member,
        channel: discord.VoiceChannel,
        announce_channel_id: int,
        excluded_channels: Set[int],
        now: float,
    ) -> None:
        key: JoinKey = (member.guild.id, member.id)

        # excluded VC => no announce, empty cache
        if channel.id in excluded_channels:
            self._join_times.pop(key, None)
            return

        data: Optional[JoinValue] = self._join_times.get(key)
        if data is None:
            return

        joined_channel_id, joined_at = data

        # join_VC != leace_vc => no announce, empty cache
        if joined_channel_id != channel.id:
            self._join_times.pop(key, None)
            return

        duration = now - joined_at
        self._join_times.pop(key, None)

        if duration <= self.threshold_seconds:
            guild = member.guild
            ch = guild.get_channel(announce_channel_id)
            if not isinstance(ch, discord.TextChannel):
                return
            
            msg = f"<@{member.id}> 入 <#{channel.id}> 偷聽完又走"
            await ch.send(msg)


async def setup(bot: commands.Bot):
    await bot.add_cog(AnnounceCog(bot))
