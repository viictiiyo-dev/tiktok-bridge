#!/usr/bin/env python3
"""TikTok Bridge como servidor MCP (stdio o Streamable HTTP).
Uso local / Smithery:
  claude mcp add tiktok-bridge --transport stdio -- "C:\\Program Files\\Python311\\python.exe" src/mcp_server.py
  python src/mcp_server.py --http --port 41245
En modo publico, tiktok_search devuelve instrucciones para REST x402 y no hace scraping gratuito.
MCP_ALLOW_FREE_SEARCH=1 permite scraping sin cobro SOLO en una instancia privada de operador.
tiktok_profile / tiktok_comments son los nombres recomendados; tiktok_perfil_info / tiktok_comments_info se mantienen por compatibilidad. En modo público muestran instrucciones REST x402 y no firman pagos.
"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mcp.server.mcpserver import MCPServer

mcp = MCPServer("tiktok-bridge")


def _free_mcp_search_enabled() -> bool:
    """Free search is opt-in; never enabled implicitly for a public MCP deployment."""
    value = os.environ.get("MCP_ALLOW_FREE_SEARCH")
    if value is None:
        env_file = Path(__file__).resolve().parent.parent / ".env"
        try:
            for line in env_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("MCP_ALLOW_FREE_SEARCH="):
                    value = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
        except OSError:
            pass
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}



# MCP runs in a separate process from REST. A sync Redis client lets both interfaces
# share normalized REST cache keys without crossing asyncio event loops.
_MCP_CACHE = {}
_MCP_CACHE_MAX_KEYS = 500


def _mcp_cache_get(key: str):
    import time
    # Reuse REST's Redis/SQLite backend, so cache hits cross process boundaries.
    try:
        import cache as shared_cache
        value = shared_cache.get_sync(key)
        if value is not None:
            return value
    except Exception:
        pass
    hit = _MCP_CACHE.get(key)
    if hit and hit[0] > time.time():
        return hit[1]
    _MCP_CACHE.pop(key, None)
    return None


def _mcp_cache_put(key: str, value: dict, ttl: int = 3600):
    import time
    try:
        import cache as shared_cache
        shared_cache.put_sync(key, value, ttl=ttl)
        return
    except Exception:
        pass
    now = time.time()
    for old_key, (expires, _) in list(_MCP_CACHE.items()):
        if expires <= now:
            _MCP_CACHE.pop(old_key, None)
    while len(_MCP_CACHE) >= _MCP_CACHE_MAX_KEYS and key not in _MCP_CACHE:
        _MCP_CACHE.pop(next(iter(_MCP_CACHE)), None)
    _MCP_CACHE[key] = (now + max(1, int(ttl)), value)


def _paid_http_hint(endpoint: str, price: str, body: dict) -> dict:
    return {
        "payment_required": True,
        "service": "TikTok Bridge",
        "method": "POST",
        "endpoint": endpoint,
        "price": price if "USDC" in price else price + " USDC",
        "currency": "USDC",
        "network": "eip155:8453",
        "body": body,
        "instruction": (
            "Este servidor MCP no puede firmar pagos x402 por ti. Envía este cuerpo al endpoint "
            "REST desde un cliente HTTP compatible con x402; acepta el reto 402 y reintenta con "
            "PAYMENT-SIGNATURE. Sin resultados se aplica free-miss."
        ),
    }


def _execute_private(key: str, fn, query_field: str = "", query_value: str = "") -> dict:
    import time
    cached = _mcp_cache_get(key)
    if isinstance(cached, dict):
        result = dict(cached)
        if query_field:
            result[query_field] = query_value
        result["cached"] = True
        result["ts"] = int(time.time())
        return result
    status, data = fn()
    if status == "retry":
        return {"error": "TikTok no respondió dentro del límite de tiempo",
                "retry_after_seconds": 60, **(data if isinstance(data, dict) else {})}
    if status == "invalid":
        return data if isinstance(data, dict) else {"error": str(data)}
    result = dict(data or {})
    if query_field:
        result[query_field] = query_value
    result["cached"] = False
    result["ts"] = int(time.time())
    # Avoid sharing a transient retry or invalid response with future MCP calls.
    _mcp_cache_put(key, result, ttl=300 if result.get("free_miss") else 3600)
    return result


@mcp.tool()
def tiktok_search(q: str, max_results: int = 20) -> str:
    """Busca vídeos públicos. En modo público entrega instrucciones REST x402; en instancia privada autorizada, devuelve JSON normalizado y cacheado."""
    query = " ".join(str(q or "").split())[:200]
    if not query:
        return json.dumps({"error": "q requerido"}, ensure_ascii=False)
    try:
        limit = int(max_results)
    except (TypeError, ValueError):
        return json.dumps({"error": "max_results debe ser un entero entre 1 y 20"}, ensure_ascii=False)
    if not 1 <= limit <= 20:
        return json.dumps({
            "error": "max_results debe estar entre 1 y 20 al precio actual de 0.08 USDC"
        }, ensure_ascii=False)
    if not _free_mcp_search_enabled():
        hint = _paid_http_hint("https://veredicto.dpdns.org/v1/tiktok/search",
                               "0.08", {"q": query, "max": limit})
        return json.dumps(hint, ensure_ascii=False)
    import tiktok_router as router
    key = router.search_cache_key(query, limit)
    result = _execute_private(key, lambda: router.run_search(query, limit), "q", query)
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
def tiktok_perfil_info(user: str) -> str:
    """Consulta el perfil público y sus publicaciones recientes en modo privado autorizado; en modo público indica cómo pagar vía REST x402."""
    username = str(user or "").strip()
    if not username:
        return json.dumps({"error": "user requerido"}, ensure_ascii=False)
    if not _free_mcp_search_enabled():
        return json.dumps(_paid_http_hint(
            "https://veredicto.dpdns.org/v1/tiktok/perfil", "0.08", {"user": username}
        ), ensure_ascii=False)
    import tiktok_router as router
    normalized = router._normalise_username(username)
    if not normalized:
        return json.dumps({"error": "user invalido: usa un nombre de usuario publico o URL de perfil TikTok"}, ensure_ascii=False)
    result = _execute_private(
        router.profile_cache_key(normalized), lambda: router.run_profile(normalized), "user", normalized
    )
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
def tiktok_comments_info(video_id: str, max_comments: int = 50) -> str:
    """Consulta comentarios públicos de un vídeo en modo privado autorizado; en modo público indica cómo pagar vía REST x402."""
    value = str(video_id or "").strip()
    if not value:
        return json.dumps({"error": "video_id requerido"}, ensure_ascii=False)
    try:
        limit = max(1, min(50, int(max_comments)))
    except (TypeError, ValueError):
        return json.dumps({"error": "max_comments debe ser un entero entre 1 y 50"}, ensure_ascii=False)
    if not _free_mcp_search_enabled():
        return json.dumps(_paid_http_hint(
            "https://veredicto.dpdns.org/v1/tiktok/comments", "0.05", {"id": value, "max": limit}
        ), ensure_ascii=False)
    import tiktok_router as router
    result = _execute_private(
        router.comments_cache_key(value, limit),
        lambda: router.run_comments(value, limit),
        "id", value
    )
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
def tiktok_profile(user: str) -> str:
    """Alias sencillo de tiktok_perfil_info para consultar perfil público y publicaciones recientes."""
    return tiktok_perfil_info(user)


@mcp.tool()
def tiktok_comments(video_id: str, max_comments: int = 50) -> str:
    """Alias sencillo de tiktok_comments_info para consultar comentarios públicos de un vídeo."""
    return tiktok_comments_info(video_id, max_comments)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="TikTok Bridge MCP")
    p.add_argument("--http", action="store_true", help="Streamable HTTP en vez de stdio")
    p.add_argument("--port", type=int, default=41245)
    a = p.parse_args()
    if a.http:
        mcp.run(transport="streamable-http", host="127.0.0.1", port=a.port)
    else:
        mcp.run()
