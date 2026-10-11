#!/usr/bin/env python3
"""Caché compartida Redis → SQLite → memoria, con expiración y límite de tamaño.

Redis es la primera opción. Si CACHE_REQUIRE_REDIS=0 y Redis no está disponible,
SQLite permite compartir resultados entre REST y MCP en procesos independientes.
La caché en memoria solo se usa si ambas opciones persistentes fallan.
"""
import json
import logging
import os
import sqlite3
import time
from pathlib import Path
from typing import Any

TTL_S = int(os.environ.get("CACHE_TTL_S", "3600"))
REDIS_URL = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379")
CACHE_REQUIRE_REDIS = os.environ.get("CACHE_REQUIRE_REDIS", "0").strip().lower() in {
    "1", "true", "yes", "on"
}
CACHE_SQLITE_PATH = Path(os.environ.get(
    "CACHE_SQLITE_PATH", str(Path(__file__).resolve().parent / "tiktok_cache.sqlite3")
))
SQLITE_MAX_KEYS = max(100, int(os.environ.get("CACHE_SQLITE_MAX_KEYS", "10000")))
MEM_MAX_KEYS = max(100, int(os.environ.get("CACHE_MEM_MAX_KEYS", "5000")))
SQLITE_BUSY_TIMEOUT_MS = max(100, int(os.environ.get("CACHE_SQLITE_BUSY_TIMEOUT_MS", "5000")))

_mem: dict[str, tuple[float, Any]] = {}
_client = None
_sync_client = None
_sync_redis_tried = False
_redis_unavailable_reason = ""
_warning_emitted = False
logger = logging.getLogger(__name__)


async def _redis():
    """Devuelve un cliente Redis async o None si el respaldo está permitido."""
    global _client, _redis_unavailable_reason, _warning_emitted
    if _client is not None:
        return _client
    try:
        import redis.asyncio as redis
        client = redis.Redis.from_url(
            REDIS_URL, decode_responses=True,
            socket_connect_timeout=1.5, socket_timeout=1.5,
            health_check_interval=30,
        )
        await client.ping()
        _client = client
        _redis_unavailable_reason = ""
        return client
    except Exception as exc:
        _redis_unavailable_reason = type(exc).__name__
        if CACHE_REQUIRE_REDIS:
            raise RuntimeError("CACHE_REQUIRE_REDIS=1 pero Redis no está disponible") from exc
        if not _warning_emitted:
            logger.warning(
                "Redis no disponible (%s); se usará caché persistente SQLite si es posible",
                _redis_unavailable_reason,
            )
            _warning_emitted = True
        return None


def _sqlite_connect():
    CACHE_SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(
        str(CACHE_SQLITE_PATH), timeout=SQLITE_BUSY_TIMEOUT_MS / 1000,
        isolation_level=None,
    )
    conn.row_factory = sqlite3.Row
    conn.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS cache_entries (
            cache_key TEXT PRIMARY KEY,
            value_json TEXT NOT NULL,
            expires_at REAL NOT NULL,
            created_at REAL NOT NULL
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cache_entries_expiry ON cache_entries(expires_at)")
    return conn


def _sqlite_get(key: str):
    now = time.time()
    conn = _sqlite_connect()
    try:
        row = conn.execute(
            "SELECT value_json, expires_at FROM cache_entries WHERE cache_key=?",
            (key,),
        ).fetchone()
        if row is None:
            return None
        if float(row["expires_at"]) <= now:
            conn.execute("DELETE FROM cache_entries WHERE cache_key=?", (key,))
            return None
        try:
            return json.loads(row["value_json"])
        except (TypeError, json.JSONDecodeError):
            conn.execute("DELETE FROM cache_entries WHERE cache_key=?", (key,))
            return None
    finally:
        conn.close()


def _sqlite_put(key: str, value: Any, ttl: int = TTL_S):
    now = time.time()
    expires = now + max(1, int(ttl))
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    conn = _sqlite_connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("DELETE FROM cache_entries WHERE expires_at<=?", (now,))
        conn.execute(
            """INSERT INTO cache_entries(cache_key,value_json,expires_at,created_at)
               VALUES(?,?,?,?)
               ON CONFLICT(cache_key) DO UPDATE SET
                 value_json=excluded.value_json,
                 expires_at=excluded.expires_at,
                 created_at=excluded.created_at""",
            (key, payload, expires, now),
        )
        excess = int(conn.execute("SELECT COUNT(*) FROM cache_entries").fetchone()[0]) - SQLITE_MAX_KEYS
        if excess > 0:
            conn.execute(
                """DELETE FROM cache_entries WHERE cache_key IN
                   (SELECT cache_key FROM cache_entries ORDER BY created_at ASC LIMIT ?)""",
                (excess,),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return True


def _mem_get(key: str):
    hit = _mem.get(key)
    if hit and hit[0] > time.time():
        return hit[1]
    _mem.pop(key, None)
    return None


def _mem_put(key: str, value: Any, ttl: int = TTL_S):
    now = time.time()
    for old_key, (expires, _) in list(_mem.items()):
        if expires <= now:
            _mem.pop(old_key, None)
    while len(_mem) >= MEM_MAX_KEYS and key not in _mem:
        _mem.pop(next(iter(_mem)), None)
    _mem[key] = (now + max(1, int(ttl)), value)
    return True


def _get_sync_redis():
    """Cliente Redis síncrono para MCP, que comparte las mismas claves que REST."""
    global _sync_client, _sync_redis_tried, _redis_unavailable_reason
    if _sync_client is not None:
        return _sync_client
    if _sync_redis_tried:
        return None
    _sync_redis_tried = True
    try:
        import redis
        client = redis.Redis.from_url(
            REDIS_URL, decode_responses=True,
            socket_connect_timeout=1.5, socket_timeout=1.5,
            health_check_interval=30,
        )
        client.ping()
        _sync_client = client
        _redis_unavailable_reason = ""
        return client
    except Exception as exc:
        _redis_unavailable_reason = type(exc).__name__
        if CACHE_REQUIRE_REDIS:
            raise RuntimeError("CACHE_REQUIRE_REDIS=1 pero Redis no está disponible") from exc
        return None


def get_sync(key: str):
    """Lectura síncrona Redis/SQLite/memoria para MCP y herramientas no-async."""
    client = _get_sync_redis()
    if client is not None:
        try:
            raw = client.get(key)
            return json.loads(raw) if raw else None
        except Exception as exc:
            global _sync_client
            _redis_unavailable_reason_local(exc)
            try:
                client.close()
            except Exception:
                pass
            _sync_client = None
            if CACHE_REQUIRE_REDIS:
                raise RuntimeError("Redis dejó de estar disponible") from exc
    if CACHE_REQUIRE_REDIS:
        raise RuntimeError("Redis obligatorio y no disponible")
    try:
        value = _sqlite_get(key)
        if value is not None:
            return value
    except Exception as exc:
        logger.warning("Lectura SQLite falló (%s); se usará memoria", type(exc).__name__)
    return _mem_get(key)


def put_sync(key: str, value: Any, ttl: int = TTL_S):
    """Escritura síncrona en la misma caché persistente que usa REST."""
    client = _get_sync_redis()
    if client is not None:
        try:
            client.setex(key, max(1, int(ttl)), json.dumps(value, ensure_ascii=False))
            return True
        except Exception as exc:
            global _sync_client
            _redis_unavailable_reason_local(exc)
            try:
                client.close()
            except Exception:
                pass
            _sync_client = None
            if CACHE_REQUIRE_REDIS:
                raise RuntimeError("Redis dejó de estar disponible") from exc
    if CACHE_REQUIRE_REDIS:
        raise RuntimeError("Redis obligatorio y no disponible")
    try:
        return _sqlite_put(key, value, ttl)
    except Exception as exc:
        logger.warning("Escritura SQLite falló (%s); se usará memoria", type(exc).__name__)
        return _mem_put(key, value, ttl)


def _redis_unavailable_reason_local(exc):
    global _redis_unavailable_reason
    _redis_unavailable_reason = type(exc).__name__


async def backend_status():
    """Estado seguro de la caché; nunca revela rutas, URLs ni credenciales."""
    try:
        client = await _redis()
    except Exception as exc:
        return {"backend": "unavailable", "warning": type(exc).__name__}
    if client is not None:
        return {"backend": "redis", "shared_between_workers": True}
    if CACHE_REQUIRE_REDIS:
        return {"backend": "unavailable", "warning": _redis_unavailable_reason or "redis-required"}
    try:
        conn = _sqlite_connect()
        try:
            conn.execute("SELECT 1").fetchone()
        finally:
            conn.close()
        return {"backend": "sqlite", "shared_between_workers": True}
    except Exception as exc:
        return {
            "backend": "memory",
            "warning": type(exc).__name__,
            "shared_between_workers": False,
        }


async def get(key: str):
    global _client, _redis_unavailable_reason
    client = await _redis()
    if client is not None:
        try:
            raw = await client.get(key)
            return json.loads(raw) if raw else None
        except Exception as exc:
            _redis_unavailable_reason = type(exc).__name__
            logger.warning("Lectura Redis falló (%s); se usará SQLite", _redis_unavailable_reason)
            try:
                await client.aclose()
            except Exception:
                pass
            _client = None
            if CACHE_REQUIRE_REDIS:
                raise RuntimeError("Redis dejó de estar disponible") from exc
    if CACHE_REQUIRE_REDIS:
        raise RuntimeError("Redis obligatorio y no disponible")
    try:
        value = _sqlite_get(key)
        if value is not None:
            return value
    except Exception as exc:
        logger.warning("Lectura SQLite falló (%s); se usará memoria", type(exc).__name__)
    return _mem_get(key)


async def put(key: str, value: Any, ttl: int = TTL_S):
    global _client, _redis_unavailable_reason
    ttl = max(1, int(ttl))
    client = await _redis()
    raw = json.dumps(value, ensure_ascii=False)
    if client is not None:
        try:
            await client.setex(key, ttl, raw)
            return True
        except Exception as exc:
            _redis_unavailable_reason = type(exc).__name__
            logger.warning("Escritura Redis falló (%s); se usará SQLite", _redis_unavailable_reason)
            try:
                await client.aclose()
            except Exception:
                pass
            _client = None
            if CACHE_REQUIRE_REDIS:
                raise RuntimeError("Redis dejó de estar disponible") from exc
    if CACHE_REQUIRE_REDIS:
        raise RuntimeError("Redis obligatorio y no disponible")
    try:
        _sqlite_put(key, value, ttl)
        # L1 in-process reduces latency; SQLite remains the shared source of truth.
        _mem_put(key, value, ttl)
        return True
    except Exception as exc:
        logger.warning("Escritura SQLite falló (%s); se usará memoria", type(exc).__name__)
        return _mem_put(key, value, ttl)


async def close():
    global _client, _sync_client
    if _client is not None:
        try:
            await _client.aclose()
        except Exception:
            pass
        _client = None
    if _sync_client is not None:
        try:
            _sync_client.close()
        except Exception:
            pass
        _sync_client = None
