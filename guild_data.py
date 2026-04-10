import asyncio
from typing import Dict, Any, Optional, List

from google.cloud import firestore

db = firestore.Client()

GUILD_CACHE: Dict[int, Dict[str, Any]] = {}

DEFAULT_GUILD_DATA: Dict[str, Any] = {
    "announce_channel_id": None,
    "announce_excluded_voice_channels": [],
}


def normalize_guild_data(data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    raw = dict(data or {})

    announce_channel_id = raw.get("announce_channel_id")
    if announce_channel_id is None:
        announce_channel_id = raw.get("channel_id")

    excluded_voice_channels = raw.get("announce_excluded_voice_channels")
    if excluded_voice_channels is None:
        excluded_voice_channels = raw.get("excluded_voice_channels")
    if excluded_voice_channels is None:
        excluded_voice_channels = raw.get("private_voice_channels")
    if excluded_voice_channels is None:
        excluded_voice_channels = []

    return {
        **raw,
        "announce_channel_id": announce_channel_id,
        "announce_excluded_voice_channels": list(excluded_voice_channels),
    }


def get_guild_ref(guild_id: int):
    return db.collection("guilds").document(str(guild_id))


async def get_guild_data(guild_id: int) -> Dict[str, Any]:
    if guild_id in GUILD_CACHE:
        return GUILD_CACHE[guild_id]

    ref = get_guild_ref(guild_id)
    doc = await asyncio.to_thread(ref.get)

    if doc.exists:
        data = normalize_guild_data(doc.to_dict())
    else:
        data = dict(DEFAULT_GUILD_DATA)
        await asyncio.to_thread(ref.set, data)

    data = normalize_guild_data(data)

    GUILD_CACHE[guild_id] = data
    return data


async def update_guild_data(guild_id: int, data: Dict[str, Any]) -> None:
    ref = get_guild_ref(guild_id)
    normalized = normalize_guild_data(data)
    await asyncio.to_thread(ref.set, normalized, True)  # merge=True

    if guild_id in GUILD_CACHE:
        GUILD_CACHE[guild_id].update(normalized)
    else:
        current = await get_guild_data(guild_id)
        current.update(normalized)
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
