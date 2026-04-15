from dotenv import load_dotenv
from discord.ext import commands
import discord
import os
import logging

from constants import PREFIX_WHITELIST
from service.cache import EnchantCache
from service.enchant_service import EnchantService

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise ValueError("No any discord token. Configure .env file first.")
TEST_GUILD_ID = 917151296287571988 # yep my lab

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        super().__init__(command_prefix=commands.when_mentioned_or("."), intents=intents)

    async def setup_hook(self):
        self.enchant_cache = EnchantCache(ttl_sec=30)
        self.enchant_service = EnchantService(self.enchant_cache)

        # load cogs
        await self.load_extension("cogs.help_cog")
        await self.load_extension("cogs.lang_cog")
        await self.load_extension("cogs.stat_cog")
        await self.load_extension("cogs.choose_cog")
        await self.load_extension("cogs.vhs_cog")
        await self.load_extension("cogs.enchant_cog")
        await self.load_extension("cogs.vaal_cog")
        await self.load_extension("cogs.arena_cog")
        await self.load_extension("cogs.announce_cog")
        
        """ test mode (only active in my guild) """
        # guild = discord.Object(id=TEST_GUILD_ID)
        # self.tree.copy_global_to(guild=guild)
        # await self.tree.sync(guild=guild)

        """ standard sync """
        await self.tree.sync()

        print("Slash commands synced.")

bot = MyBot()



@bot.event
async def on_ready():
    """  Bot on ready """
    logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    print(f"Logged in as {bot.user}")


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    content = message.content or ""

    if content.startswith("."):
        cmd = content[1:].split(maxsplit=1)[0].lower()

        if cmd not in PREFIX_WHITELIST:
            return

    await bot.process_commands(message)


bot.run(TOKEN)

