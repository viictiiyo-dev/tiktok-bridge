#!/usr/bin/env python3
"""Caché 1h task 4: redis.asyncio + fallback memoria.
Keys: tiktok:search:{q}:{max} | tiktok:perfil:{user} | tiktok:comments:{id}.
Gotchas Context7: setex(name, time, value), decode_responses=True, aclose() explícito.
Sin Redis disponible → memoria con expiración (dev ok, prod exige Redis).
"""
import json
import os
import time

TTL_S = int(os.environ.get("CACHE_TTL_S", "3600"))
REDIS_URL = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379")

_mem: dict = {}
_client = None


async def _redis():
    global _client
    if _client is not None:
        return _client
    try:
        import redis.asyncio as redis
        c = redis.Redis.from_url(REDIS_URL, decode_responses=True)
        await c.ping()
        _client = c
        return c
    except Exception:
        return None


async def get(key: str):
    c = await _redis()
    if c is not None:
        try:
            raw = await c.get(key)
            return json.loads(raw) if raw else None
        except Exception:
            return None
    hit = _mem.get(key)
    if hit and hit[0] > time.time():
        return hit[1]
    _mem.pop(key, None)
    return None


async def put(key: str, value: dict, ttl: int = TTL_S):
    c = await _redis()
    raw = json.dumps(value, ensure_ascii=False)
    if c is not None:
        try:
            await c.setex(key, ttl, raw)
            return True
        except Exception:
            pass
    _mem[key] = (time.time() + ttl, value)
    return True


async def close():
    global _client
    if _client is not None:
        try:
            await _client.aclose()
        except Exception:
            pass
        _client = None
