import os

from discord.ext import commands
import dotenv
from google.cloud import firestore
import asyncio
    

dotenv.load_dotenv()
GOOGLE_CLOUD_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT")
db = firestore.Client(project=GOOGLE_CLOUD_PROJECT)

BOT_OWNER_ID = 395223486752358400

class AdminCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="resetusers")
    async def reset_users(self, ctx):
        if ctx.author.id != BOT_OWNER_ID:
            await ctx.send("🚫 You are not authorized to perform this action.")
            return

        await ctx.send("⏳ Deleting all Firestore user records...")
        users_ref = db.collection("users")
        docs = users_ref.stream()

        count = 0
        async for doc in asyncio.to_thread(lambda: list(docs)):
            doc.reference.delete()
            count += 1

        await ctx.send(f"✅ Deleted `{count}` user documents from Firestore.")
