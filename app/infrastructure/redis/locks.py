from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator
from uuid import uuid4

from app.agent.errors import ThreadLockedError


class RedisThreadLockManager:
    def __init__(self, *, redis_url: str, ttl_seconds: int):
        self.redis_url = redis_url
        self.ttl_seconds = ttl_seconds
        self._client = None

    async def _redis(self):
        if self._client is None:
            from redis.asyncio import Redis

            self._client = Redis.from_url(self.redis_url, decode_responses=True)
        return self._client

    @asynccontextmanager
    async def acquire(self, *, tenant_id: str, thread_id: str) -> AsyncIterator[None]:
        client = await self._redis()
        key = f"agent:v2:lock:{tenant_id}:{thread_id}"
        token = str(uuid4())
        acquired = await client.set(key, token, nx=True, ex=self.ttl_seconds)
        if not acquired:
            raise ThreadLockedError()
        try:
            yield
        finally:
            script = """
            if redis.call("get", KEYS[1]) == ARGV[1] then
                return redis.call("del", KEYS[1])
            end
            return 0
            """
            await client.eval(script, 1, key, token)
