from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncIterator

from app.agent.errors import ThreadLockedError


@dataclass
class _LockEntry:
    lock: asyncio.Lock
    expires_at: float


class ThreadLockManager:
    def __init__(self, ttl_seconds: int):
        self.ttl_seconds = ttl_seconds
        self._locks: dict[str, _LockEntry] = {}
        self._guard = asyncio.Lock()

    @asynccontextmanager
    async def acquire(self, *, tenant_id: str, thread_id: str) -> AsyncIterator[None]:
        key = f"{tenant_id}:{thread_id}"
        async with self._guard:
            self._cleanup_expired()
            entry = self._locks.get(key)
            if not entry:
                entry = _LockEntry(lock=asyncio.Lock(), expires_at=time.monotonic() + self.ttl_seconds)
                self._locks[key] = entry
            elif entry.lock.locked():
                raise ThreadLockedError()
            entry.expires_at = time.monotonic() + self.ttl_seconds
        await entry.lock.acquire()
        try:
            yield
        finally:
            entry.lock.release()
            entry.expires_at = time.monotonic() + self.ttl_seconds

    def _cleanup_expired(self) -> None:
        now = time.monotonic()
        expired = [
            key
            for key, entry in self._locks.items()
            if not entry.lock.locked() and entry.expires_at < now
        ]
        for key in expired:
            self._locks.pop(key, None)

