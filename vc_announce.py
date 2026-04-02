import os
import json

announce_channel_path = os.path.join(os.path.dirname(__file__), "data/announce_channel.json")

announce_cache = {}

async def load_channel_data():
    global announce_cache
    try:
        with open(announce_channel_path, 'r') as f:
            announce_cache = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        announce_cache = {}
        save_channel_data()
    return announce_cache

def save_channel_data():
    with open(announce_channel_path, 'w') as f:
        json.dump(announce_cache, f, indent=4)

async def get_announce_channel(guild_id):
    if not announce_cache:
        await load_channel_data()
    return announce_cache.get(str(guild_id), {}).get("channel_id")

async def set_announce_channel(guild, channel):
    await load_channel_data()
    guild_id = str(guild.id)
    channel_id = channel.id

    if guild_id in announce_cache and announce_cache[guild_id]["channel_id"] == channel_id:
        return False

    announce_cache[guild_id] = {"channel_id": channel_id}
    save_channel_data()
    return True	# announcement channel changed