from __future__ import annotations
import discord
from msg_utils import MessageResolver
from constants import Command, CommandStatus

class HelpService:
    async def build_help_embed(self, guild_id: int, user_id: int) -> discord.Embed:
        resolver = MessageResolver(guild_id, user_id)

        embed = discord.Embed(
            title=await resolver.get(Command.SYS.command_name, "help_title"),
            description="",
            color=discord.Color.blue(),
        )

        # only show features that is not hidden
        categories: dict[CommandStatus, list[str]] = {
            status: [] for status in CommandStatus if status != CommandStatus.HIDDEN
        }

        # check language
        section_titles = await resolver.get(Command.SYS.command_name, "help_section")

        for command in Command:
            if command.status == CommandStatus.HIDDEN:
                continue
            categories[command.status].append("・" + f"/{command.command_name}")

        for status, cmds in categories.items():
            if not cmds:
                continue
            key = status.name.lower()
            section_name = section_titles.get(key, status.value)
            embed.add_field(name=section_name, value="\n".join(cmds), inline=False)

        return embed
