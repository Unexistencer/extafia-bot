from user_data import *


# --------------- Payment --------------------
async def arena_pay(guild_id, user_id, amount):
    ref = get_user_ref(guild_id, user_id)
    doc = ref.get().to_dict()
    current = doc.get("currency", 0)
    ref.update({"currency": max(0, current - amount)})
    
async def safe_pay(guild_id, user_id, amount) -> bool:
    ref = get_user_ref(guild_id, user_id)
    doc = ref.get().to_dict()
    current = doc.get("currency", 0)
    if current < amount:
        return False, current    # reject
    current = current - amount
    return True, current
