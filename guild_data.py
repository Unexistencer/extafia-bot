import asyncio
from typing import Dict, Any, Optional, List

from google.cloud import firestore

db = firestore.Client()

GUILD_CACHE: Dict[int, Dict[str, Any]] = {}


def get_guild_ref(guild_id: int):
    return db.collection("guilds").document(str(guild_id))


async def get_guild_data(guild_id: int) -> Dict[str, Any]:
    if guild_id in GUILD_CACHE:
        return GUILD_CACHE[guild_id]

    ref = get_guild_ref(guild_id)
    doc = await asyncio.to_thread(ref.get)

    if doc.exists:
        data = doc.to_dict() or {}
    else:
        data = {
            "announce_channel_id": None,
            "announce_excluded_voice_channels": [],
        }
        await asyncio.to_thread(ref.set, data)

    data.setdefault("announce_channel_id", None)
    data.setdefault("announce_excluded_voice_channels", [])

    GUILD_CACHE[guild_id] = data
    return data


async def update_guild_data(guild_id: int, data: Dict[str, Any]) -> None:
    ref = get_guild_ref(guild_id)
    await asyncio.to_thread(ref.set, data, True)  # merge=True

    if guild_id in GUILD_CACHE:
        GUILD_CACHE[guild_id].update(data)
    else:
        current = await get_guild_data(guild_id)
        current.update(data)
        GUILD_CACHE[guild_id] = current



async def get_announce_channel(guild_id: int) -> Optional[int]:
    data = await get_guild_data(guild_id)
    return data.get("announce_channel_id")


async def set_announce_channel(guild_id: int, channel_id: Optional[int]) -> None:
    await update_guild_data(guild_id, {"announce_channel_id": channel_id})


async def get_excluded_voice_channels(guild_id: int) -> List[int]:
    data = await get_guild_data(guild_id)
    return list(data.get("announce_excluded_voice_channels", []))


async def add_excluded_voice_channel(guild_id: int, channel_id: int) -> None:
    data = await get_guild_data(guild_id)
    lst: List[int] = data.get("announce_excluded_voice_channels", [])
    if channel_id not in lst:
        lst.append(channel_id)
        await update_guild_data(guild_id, {"announce_excluded_voice_channels": lst})


async def remove_excluded_voice_channel(guild_id: int, channel_id: int) -> None:
    data = await get_guild_data(guild_id)
    lst: List[int] = data.get("announce_excluded_voice_channels", [])
    if channel_id in lst:
        lst.remove(channel_id)
        await update_guild_data(guild_id, {"announce_excluded_voice_channels": lst})


__all__ = [
    "get_guild_data",
    "update_guild_data",
    "get_announce_channel",
    "set_announce_channel",
    "get_excluded_voice_channels",
    "add_excluded_voice_channel",
    "remove_excluded_voice_channel",
]
