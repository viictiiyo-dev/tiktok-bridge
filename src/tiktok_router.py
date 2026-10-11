"""Router TikTok por detrás (paso 3). Contrato: nunca exponer actorId al agente.
Por delante: {videos:[{id,desc,autor,likes,fecha}]}. Por detrás: Apify run + Dataset.
Free-miss si 0 resultados. Caché 1h key tiktok:q.
"""
import os

ACTOR_SEARCH = os.environ.get("APIFY_ACTOR_SEARCH", "clockworks~tiktok-scraper")
ACTOR_FALLBACK = os.environ.get("APIFY_ACTOR_FALLBACK", "clockworks~free-tiktok-scraper")
PROXY_COUNTRY = os.environ.get("PROXY_COUNTRY", "ES")

PRICE_SEARCH = "80000"  # 0.08 USDC
PRICE_PERFIL = "80000"
PRICE_COMMENTS = "50000"  # 0.05 USDC


def build_search_input(q: str, max_results: int = 20) -> dict:
    # schema real clockworks~tiktok-scraper (build LODXsZPXqHeTq0Ssg): searchQueries[], resultsPerPage, proxyCountryCode.
    return {"searchQueries": [q], "resultsPerPage": max(1, min(50, max_results)),
            "proxyCountryCode": PROXY_COUNTRY, "shouldDownloadVideos": False,
            "shouldDownloadCovers": False, "shouldDownloadAvatars": False}


def normalize_dataset(items: list) -> dict:
    videos = []
    for it in items or []:
        author = it.get("author") or it.get("authorMeta") or {}
        stats = it.get("stats") or {}
        video = it.get("video") or {}
        tags = it.get("hashtags") or [h.get("hashtagName", h) if isinstance(h, dict) else h
                                      for h in (it.get("contents") or [])] or []
        if isinstance(author, dict):
            autor = author.get("uniqueId") or author.get("nickName") or author.get("name") or ""
        else:
            autor = author
        likes = stats.get("diggCount", it.get("diggCount", it.get("likes", 0)))
        fecha = it.get("createTime") or it.get("createTimeISO", "")
        cover = video.get("cover", "") if isinstance(video, dict) else ""
        if not cover and isinstance(it.get("covers"), list) and it["covers"]:
            cover = it["covers"][0]
        videos.append({
            "id": str(it.get("id", "")),
            "desc": (it.get("desc") or it.get("text") or "")[:280],
            "autor": autor,
            "likes": likes,
            "fecha": fecha,
            "hashtags": tags if isinstance(tags, list) else [],
            "cover": cover,
        })
    return {"videos": videos, "free_miss": len(videos) == 0}


# --- Task 3.1/3.2: run-sync + fallback + coste + healthcheck ---
# gotcha Context7 Apify: POST /v2/acts/{actorId}/run-sync-get-dataset-items?token=&timeout=50
# devuelve items directo (sin polling). Timeout nuestro 60s → 202 + retry-hint.
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

APIFY_BASE = "https://api.apify.com"
SYNC_TIMEOUT_S = 50
COSTLOG_PATH = Path(__file__).resolve().parent / "coste_tiktok.jsonl"
_fail_count: dict = {}


def _token() -> str:
    tok = os.environ.get("APIFY_TOKEN", "").strip()
    if tok:
        return tok
    try:
        return (Path(__file__).resolve().parent.parent / "apify_token.txt").read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def log_coste(actor: str, kind: str, items_n: int, ms: int, ok: bool):
    # Sin precio exacto por API: estimamos ~$0.015/run (compute+proxy ES) para vigilar margen 3x a $0.08.
    try:
        with open(COSTLOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": int(time.time()), "actor": actor, "kind": kind,
                                "items": items_n, "ms": ms, "ok": ok,
                                "cost_est_usd": 0.015 if ok else 0.0}) + "\n")
    except OSError:
        pass


def _run_sync(actor: str, payload: dict) -> tuple:
    tok = _token()
    if not tok:
        return None, "sin APIFY_TOKEN"
    url = f"{APIFY_BASE}/v2/acts/{urllib.parse.quote(actor, safe='~')}/run-sync-get-dataset-items?token={tok}&timeout={SYNC_TIMEOUT_S}"
    body = json.dumps(payload).encode()
    t0 = int(time.time() * 1000)
    try:
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=SYNC_TIMEOUT_S + 10) as r:
            items = json.load(r)
        ms = int(time.time() * 1000) - t0
        log_coste(actor, "search", len(items or []), ms, True)
        _fail_count[actor] = 0
        return items or [], ""
    except Exception as e:
        ms = int(time.time() * 1000) - t0
        log_coste(actor, "search", 0, ms, False)
        _fail_count[actor] = _fail_count.get(actor, 0) + 1
        return None, type(e).__name__


def run_search(q: str, max_results: int = 20) -> dict:
    """Miss path: run-sync top → fallback → free-miss. Nunca expone actorId. Retorna (status, body).
    status: 'ok' | 'retry' (202) | 'miss' (free-miss 200)."""
    payload = build_search_input(q, max_results)
    order = [(ACTOR_FALLBACK, ACTOR_SEARCH) if _fail_count.get(ACTOR_SEARCH, 0) >= 3
             else (ACTOR_SEARCH, ACTOR_FALLBACK)]
    first, second = order[0]
    items, err = _run_sync(first, payload)
    if items is not None:
        return ("miss", normalize_dataset(items)) if not items else ("ok", normalize_dataset(items))
    # timeout/duro o error → fallback una vez
    items2, _ = _run_sync(second, payload)
    if items2 is not None:
        return ("miss", normalize_dataset(items2)) if not items2 else ("ok", normalize_dataset(items2))
    # captcha duro / ambos caídos: free-miss + reintento encolado, nunca 500.
    return ("retry", {"retry_hint": "reintenta en 60s", "q": q, "backend_error": err})


def actor_health() -> dict:
    # switch auto: si top falla 3 seguidas, el router debe preferir fallback (lo lee server_v1).
    return {"top": ACTOR_SEARCH, "top_fails": _fail_count.get(ACTOR_SEARCH, 0),
            "fallback": ACTOR_FALLBACK, "fallback_fails": _fail_count.get(ACTOR_FALLBACK, 0),
            "prefer_fallback": _fail_count.get(ACTOR_SEARCH, 0) >= 3}
