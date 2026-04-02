from __future__ import annotations
import time, asyncio
from dataclasses import dataclass, field
from typing import Dict, List, Optional

@dataclass
class UserState:
    currency: int
    affixes: List[int]
    affix_values: List[int]
    is_corrupted: bool
    update_time: Optional[str] = None # update to firestore

@dataclass
class CacheEntry:
    state: UserState
    dirty: bool = False
    last_touch: float = field(default_factory=time.time)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

class EnchantCache:
    def __init__(self, ttl_sec: int = 30, max_users: int = 5000):
        self.ttl = ttl_sec
        self.max_users = max_users
        self._store: Dict[str, CacheEntry] = {}

    def _key(self, guild_id: int, user_id: int) -> str:
        return f"{guild_id}:{user_id}"

    async def get(self, guild_id: int, user_id: int) -> Optional[CacheEntry]:
        return self._store.get(self._key(guild_id, user_id))

    async def put(self, guild_id: int, user_id: int, state: UserState, *, dirty=False) -> CacheEntry:
        key = self._key(guild_id, user_id)
        ce = self._store.get(key)
        if ce is None:
            ce = CacheEntry(state=state, dirty=dirty)
            self._store[key] = ce
        else:
            ce.state = state
            ce.dirty = dirty or ce.dirty
        ce.last_touch = time.time()
        await self._evict_if_needed()
        return ce

    async def mark_dirty(self, guild_id: int, user_id: int):
        ce = await self.get(guild_id, user_id)
        if ce:
            ce.dirty = True
            ce.last_touch = time.time()

    async def due_entries(self) -> Dict[str, CacheEntry]:
        now = time.time()
        return {k: v for k, v in self._store.items() if v.dirty and (now - v.last_touch) >= self.ttl}

    async def remove(self, guild_id: int, user_id: int):
        self._store.pop(self._key(guild_id, user_id), None)

    async def _evict_if_needed(self):
        if len(self._store) <= self.max_users:
            return
        clean = [(k, v) for k, v in self._store.items() if not v.dirty]
        if not clean:
            return
        clean.sort(key=lambda kv: kv[1].last_touch)
        k, _ = clean[0]
        self._store.pop(k, None)
