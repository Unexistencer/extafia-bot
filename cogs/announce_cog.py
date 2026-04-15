import time
from typing import Dict, List, Optional, Set, Tuple

import discord
from discord import app_commands
from discord.ext import commands

from guild_data import (
    add_excluded_voice_channel,
    get_announce_channel,
    get_excluded_voice_channels,
    remove_excluded_voice_channel,
    set_announce_channel,
)

JoinKey = Tuple[int, int]
JoinValue = Tuple[int, float]


class AnnounceCog(commands.GroupCog, name="announce"):
    """leave detect + announce channel"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._join_times: Dict[JoinKey, JoinValue] = {}
        self.threshold_seconds: float = 5.0

    # --------- Prefix Commands ---------
    @commands.group(name="announce", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def announce_prefix(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send("Usage: `.announce <set|unset|private_add|private_remove|private_list>`")

    # --------- Slash Commands ---------
    @app_commands.command(name="set", description="Set this text channel as the announce channel")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def cmd_set(self, interaction: discord.Interaction):
        if not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message("This command must be used in a text channel.", ephemeral=True)
            return

        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        await set_announce_channel(guild.id, interaction.channel.id)
        await interaction.response.send_message(
            f"Announcement channel set to <#{interaction.channel.id}>.",
            ephemeral=False,
        )

    @announce_prefix.command(name="set")
    @commands.has_permissions(manage_guild=True)
    async def announce_set_prefix(self, ctx: commands.Context):
        if not isinstance(ctx.channel, discord.TextChannel):
            await ctx.send("This command must be used in a text channel.")
            return

        guild = ctx.guild
        if guild is None:
            await ctx.send("This command can only be used in a server.")
            return

        await set_announce_channel(guild.id, ctx.channel.id)
        await ctx.send(f"Announcement channel set to <#{ctx.channel.id}>.")

    @app_commands.command(name="unset", description="Disable the announce channel")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def cmd_unset(self, interaction: discord.Interaction):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        await set_announce_channel(guild.id, None)
        await interaction.response.send_message("Announcement channel disabled.", ephemeral=True)

    @announce_prefix.command(name="unset")
    @commands.has_permissions(manage_guild=True)
    async def announce_unset_prefix(self, ctx: commands.Context):
        guild = ctx.guild
        if guild is None:
            await ctx.send("This command can only be used in a server.")
            return

        await set_announce_channel(guild.id, None)
        await ctx.send("Announcement channel disabled.")

    @app_commands.command(name="private_add", description="Exclude a voice channel from leave announcements")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def cmd_private_add(self, interaction: discord.Interaction, voice_channel: discord.VoiceChannel):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        await add_excluded_voice_channel(guild.id, voice_channel.id)
        await interaction.response.send_message(
            f"Added `{voice_channel.name}` to the excluded voice channels.",
            ephemeral=True,
        )

    @announce_prefix.command(name="private_add")
    @commands.has_permissions(manage_guild=True)
    async def announce_private_add_prefix(self, ctx: commands.Context, voice_channel: discord.VoiceChannel):
        guild = ctx.guild
        if guild is None:
            await ctx.send("This command can only be used in a server.")
            return

        await add_excluded_voice_channel(guild.id, voice_channel.id)
        await ctx.send(f"Added `{voice_channel.name}` to the excluded voice channels.")

    @app_commands.command(name="private_remove", description="Remove a voice channel from the exclusion list")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def cmd_private_remove(self, interaction: discord.Interaction, voice_channel: discord.VoiceChannel):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        await remove_excluded_voice_channel(guild.id, voice_channel.id)
        await interaction.response.send_message(
            f"Removed `{voice_channel.name}` from the excluded voice channels.",
            ephemeral=True,
        )

    @announce_prefix.command(name="private_remove")
    @commands.has_permissions(manage_guild=True)
    async def announce_private_remove_prefix(self, ctx: commands.Context, voice_channel: discord.VoiceChannel):
        guild = ctx.guild
        if guild is None:
            await ctx.send("This command can only be used in a server.")
            return

        await remove_excluded_voice_channel(guild.id, voice_channel.id)
        await ctx.send(f"Removed `{voice_channel.name}` from the excluded voice channels.")

    @app_commands.command(name="private_list", description="Show excluded voice channels")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def cmd_private_list(self, interaction: discord.Interaction):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        text = await self._build_private_list_text(guild)
        await interaction.response.send_message(text, ephemeral=True)

    @announce_prefix.command(name="private_list")
    @commands.has_permissions(manage_guild=True)
    async def announce_private_list_prefix(self, ctx: commands.Context):
        guild = ctx.guild
        if guild is None:
            await ctx.send("This command can only be used in a server.")
            return

        text = await self._build_private_list_text(guild)
        await ctx.send(text)

    async def _build_private_list_text(self, guild: discord.Guild) -> str:
        excluded_ids: List[int] = await get_excluded_voice_channels(guild.id)
        if not excluded_ids:
            return "No excluded voice channels are configured."

        lines: List[str] = []
        for channel_id in excluded_ids:
            channel = guild.get_channel(channel_id)
            if isinstance(channel, discord.VoiceChannel):
                lines.append(f"- `{channel.name}` (ID: {channel_id})")
            else:
                lines.append(f"- (deleted channel) ID: {channel_id}")
        return "Excluded voice channels:\n" + "\n".join(lines)

    # --------- listener ---------
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
            return

        excluded_list = await get_excluded_voice_channels(guild.id)
        excluded_channels: Set[int] = set(excluded_list)
        now = time.monotonic()

        # Channel A -> B
        if before.channel is not None and after.channel is not None:
            if before.channel.id != after.channel.id:
                await self._handle_leave(member, before.channel, announce_channel_id, excluded_channels, now)
                self._handle_join(member, after.channel, excluded_channels, now)
            return

        # None -> Channel A
        if before.channel is None and after.channel is not None:
            self._handle_join(member, after.channel, excluded_channels, now)
            return

        # Channel A -> None
        if before.channel is not None and after.channel is None:
            await self._handle_leave(member, before.channel, announce_channel_id, excluded_channels, now)

    # --------- utils ---------
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
        # join_VC != leave_vc => no announce, empty cache
        if joined_channel_id != channel.id:
            self._join_times.pop(key, None)
            return

        duration = now - joined_at
        self._join_times.pop(key, None)

        if duration <= self.threshold_seconds:
            guild = member.guild
            announce_channel = guild.get_channel(announce_channel_id)
            if not isinstance(announce_channel, discord.TextChannel):
                return

            await announce_channel.send(f"<@{member.id}> left <#{channel.id}> quickly")


async def setup(bot: commands.Bot):
    await bot.add_cog(AnnounceCog(bot))
