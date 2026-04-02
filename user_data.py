import asyncio
from google.cloud import firestore
from constants import Language, SeasonalData, TotalData

db = firestore.Client()

USER_CACHE = {}


def get_user_ref(guild_id, user_id):
    return db.collection("users").document(f"{guild_id}_{user_id}")


async def create_account(guild_id, user_id):
    ref = get_user_ref(guild_id, user_id)
    doc = await asyncio.to_thread(ref.get)
    if not doc.exists:
        await asyncio.to_thread(ref.set, {
            "language": "en",
            "currency": 100000,
            "data_seasonal": SeasonalData().to_dict(),
            "data_total": TotalData().to_dict(),
            "affixes": [],
            "affix_values": [],
            "is_corrupted": False
        })



def get_cache_key(guild_id, user_id):
    return f"{guild_id}_{user_id}"



async def get_user_data(guild_id, user_id):
    key = f"{guild_id}_{user_id}"
    if key in USER_CACHE:
        return USER_CACHE[key]

    user_ref = db.collection("users").document(key)
    user_doc = await asyncio.to_thread(user_ref.get)
    if user_doc.exists:
        user_data = user_doc.to_dict()
    else:
        user_data = {
            "language": "en",
            "currency": 1000000,
            "data_seasonal": SeasonalData().to_dict(),
            "data_total": TotalData().to_dict(),
            "affixes": [],
            "affix_values": [],
            "is_corrupted": False
        }
        await asyncio.to_thread(user_ref.set, user_data)

    USER_CACHE[key] = user_data
    return user_data

async def get_user_language(guild_id, user_id):
    user_data = await get_user_data(guild_id, user_id)
    return user_data.get("language", Language.EN)

async def update_user_data(guild_id, user_id, data: dict):
    key = get_cache_key(guild_id, user_id)
    user_ref = get_user_ref(guild_id, user_id)
    await asyncio.to_thread(user_ref.set, data, merge=True)

    if key in USER_CACHE:
        USER_CACHE[key].update(data)

async def get_seasonal_data(guild_id, user_id) -> SeasonalData:
    user = await get_user_data(guild_id, user_id)
    return SeasonalData.from_doc(user.get("data_seasonal"))

async def save_seasonal_data(guild_id, user_id, sd: SeasonalData):
    await update_user_data(guild_id, user_id, {"data_seasonal": sd.to_dict()})

async def get_total_data(guild_id, user_id) -> TotalData:
    user = await get_user_data(guild_id, user_id)
    return TotalData.from_doc(user.get("data_total"))

async def save_total_data(guild_id, user_id, td: TotalData):
    await update_user_data(guild_id, user_id, {"data_total": td.to_dict()})


def set_write_fields(user_data: dict, fields: list[str]) -> dict:
    """
    :param user_data: cache
    :param fields: write field
    :return: dict update_user_data
    """
    return {field: user_data[field] for field in fields if field in user_data}

__all__ = [
    "get_user_data",
    "get_user_language",
    "update_user_data",
    "get_user_ref",
    "set_write_fields",
    "get_seasonal_data",
    "save_seasonal_data",
    "get_total_data",
    "save_total_data",
]