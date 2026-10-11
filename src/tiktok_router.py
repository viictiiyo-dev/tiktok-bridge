"""Router TikTok por detrás (paso 3). Contrato: nunca exponer actorId al agente.
Por delante: {videos:[{id,desc,autor,likes,fecha}]}. Por detrás: Apify run + Dataset.
Free-miss si 0 resultados. Caché 1h key tiktok:q.
"""
import os
import contextvars


def _actor_setting(name: str, default: str) -> str:
    """Un valor vacío usa el fallback por defecto; none/off/0 desactiva la fuente."""
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    value = raw.strip()
    if value.casefold() in {"none", "off", "disabled", "0"}:
        return ""
    return value


ACTOR_SEARCH = _actor_setting("APIFY_ACTOR_SEARCH", "clockworks~tiktok-scraper")
ACTOR_FALLBACK = _actor_setting("APIFY_ACTOR_FALLBACK", "clockworks~free-tiktok-scraper")
ACTOR_PROFILE = _actor_setting("APIFY_ACTOR_PROFILE", "clockworks~tiktok-profile-scraper")
ACTOR_COMMENTS = _actor_setting("APIFY_ACTOR_COMMENTS", "clockworks~tiktok-comments-scraper")
ACTOR_SEARCH_QUALITY_FALLBACK = _actor_setting("APIFY_ACTOR_SEARCH_QUALITY_FALLBACK", "apidojo~tiktok-scraper")
ACTOR_PROFILE_FALLBACK = _actor_setting("APIFY_ACTOR_PROFILE_FALLBACK", "apidojo~tiktok-profile-scraper")
ACTOR_COMMENTS_FALLBACK = _actor_setting("APIFY_ACTOR_COMMENTS_FALLBACK", "apidojo~tiktok-comments-scraper")
PROXY_COUNTRY = os.environ.get("PROXY_COUNTRY", "ES").strip().upper() or "ES"
SEARCH_BUDGET_S = max(10, min(55, int(os.environ.get("TIKTOK_SEARCH_BUDGET_S", "48"))))
SYNC_TIMEOUT_S = max(5, min(30, int(os.environ.get("APIFY_SYNC_TIMEOUT_S", "18"))))

# Corrige costes de scraping por consulta. Los precios son tarifas públicas de
# referencia "desde", no una conciliación de la factura real de la cuenta Apify.
_COST_REQUEST_ID = contextvars.ContextVar("tiktok_bridge_cost_request_id", default="")
_PUBLIC_PPR_USD_PER_1000 = {
    ("clockworks~tiktok-scraper", "search"): 1.70,
    ("clockworks~free-tiktok-scraper", "search"): 1.00,
    ("apidojo~tiktok-scraper", "search"): 0.30,
    ("clockworks~tiktok-profile-scraper", "perfil"): 1.00,
    ("apidojo~tiktok-profile-scraper", "perfil"): 0.30,
    ("clockworks~tiktok-comments-scraper", "comments"): 0.50,
    ("apidojo~tiktok-comments-scraper", "comments"): 0.30,
}

def set_cost_request_id(request_id: str):
    """Asocia costes de proveedores con una petición pagada sin registrar sus datos privados."""
    return _COST_REQUEST_ID.set(str(request_id or "")[:100])

def reset_cost_request_id(token) -> None:
    _COST_REQUEST_ID.reset(token)

PRICE_SEARCH = "80000"  # 0.08 USDC
PRICE_PERFIL = "80000"
PRICE_COMMENTS = "50000"  # 0.05 USDC



def build_search_input(q: str, max_results: int = 20) -> dict:
    """Construye input compatible con Clockworks; limita cantidades y no descarga media."""
    query = " ".join(str(q or "").split())[:200]
    try:
        limit = max(1, min(50, int(max_results)))
    except (TypeError, ValueError):
        limit = 20
    return {
        "searchQueries": [query],
        "resultsPerPage": limit,
        "proxyCountryCode": PROXY_COUNTRY,
        "shouldDownloadVideos": False,
        "shouldDownloadCovers": False,
        "shouldDownloadAvatars": False,
    }


def _first_value(*values, default=None):
    for value in values:
        if value is None or value == "" or value == [] or value == {}:
            continue
        return value
    return default


def _as_dict(value):
    return value if isinstance(value, dict) else {}


def _normalise_tags(value) -> list:
    if value is None:
        return []
    if isinstance(value, str):
        values = [part.strip() for part in value.split(",")]
    elif isinstance(value, list):
        values = value
    else:
        return []
    output = []
    seen = set()
    for tag in values:
        if isinstance(tag, dict):
            tag = _first_value(tag.get("name"), tag.get("hashtagName"),
                               tag.get("tagName"), tag.get("title"), default="")
        tag = str(tag or "").strip().lstrip("#")
        if not tag:
            continue
        identity = tag.casefold()
        if identity not in seen:
            seen.add(identity)
            output.append(tag)
    return output


def _normalise_date(value):
    """Devuelve fechas ISO-8601 UTC; acepta epoch segundos/milisegundos e ISO."""
    from datetime import datetime, timezone
    if value is None or value == "":
        return ""
    if isinstance(value, (int, float)) or (isinstance(value, str) and value.strip().isdigit()):
        try:
            epoch = float(value)
            if epoch > 100_000_000_000:
                epoch /= 1000.0
            if epoch <= 0:
                return ""
            return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        except (ValueError, OverflowError, OSError):
            return str(value)
    text = str(value).strip()
    if not text:
        return ""
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    except (ValueError, OverflowError):
        return text


def _normalise_url(value):
    """Conserva solo URLs públicas de TikTok; limpia query/fragment de seguimiento."""
    if isinstance(value, dict):
        value = _first_value(value.get("url"), value.get("shareUrl"), value.get("webVideoUrl"), default="")
    raw = str(value or "").strip()
    if not raw:
        return ""
    if raw.startswith("//"):
        raw = "https:" + raw
    if not raw.startswith(("https://", "http://")):
        return ""
    try:
        parsed = urllib.parse.urlsplit(raw)
    except ValueError:
        return ""
    host = (parsed.hostname or "").lower()
    if host not in {"tiktok.com", "www.tiktok.com", "m.tiktok.com", "vm.tiktok.com", "vt.tiktok.com", "t.tiktok.com"}:
        return ""
    return urllib.parse.urlunsplit(("https", host, parsed.path or "/", "", ""))


def _normalise_media_url(value):
    if isinstance(value, dict):
        value = _first_value(value.get("url"), value.get("coverUrl"), value.get("src"), default="")
    raw = str(value or "").strip()
    if raw.startswith("//"):
        raw = "https:" + raw
    return raw if raw.startswith("https://") else ""


def normalize_dataset(items: list) -> dict:
    """Normaliza múltiples esquemas Apify a un único contrato utilizable."""
    videos = []
    seen_ids = set()
    for item in items or []:
        if not isinstance(item, dict):
            continue
        author = _first_value(item.get("authorMeta"), item.get("author"),
                              item.get("channel"), item.get("authorInfo"), default={})
        author = _as_dict(author)
        stats = _as_dict(_first_value(item.get("stats"), item.get("statistics"), default={}))
        video = _as_dict(item.get("video"))
        video_meta = _as_dict(item.get("videoMeta"))
        channel = _as_dict(item.get("channel"))
        video_id = str(_first_value(item.get("id"), item.get("videoId"),
                                    item.get("aweme_id"), item.get("itemId"), default="")).strip()
        # Un resultado sin ID no puede utilizarse para abrir el vídeo ni consultar comentarios.
        if not video_id or video_id in seen_ids:
            continue
        seen_ids.add(video_id)

        author_user = _first_value(author.get("uniqueId"), author.get("username"),
                                   author.get("userName"), author.get("handle"),
                                   channel.get("uniqueId"), channel.get("username"), default="")
        author_name = _first_value(author.get("nickName"), author.get("nickname"),
                                   author.get("displayName"), author.get("name"),
                                   channel.get("name"), channel.get("title"), default="")
        author_value = author_user or author_name
        if not author_value and isinstance(item.get("author"), str):
            author_value = item.get("author")

        desc = str(_first_value(item.get("desc"), item.get("text"),
                                item.get("title"), item.get("caption"), default="") or "")[:280]
        tags = _normalise_tags(_first_value(item.get("hashtags"), item.get("contents"), default=[]))
        create_value = _first_value(item.get("createTimeISO"), item.get("uploadedAt"),
                                    item.get("uploadedAtFormatted"), item.get("createTime"),
                                    item.get("createTimeStamp"), item.get("timestamp"), default="")
        fecha = _normalise_date(create_value)

        likes = _first_value(item.get("diggCount"), item.get("likes"),
                             stats.get("diggCount"), stats.get("likes"), default=None)
        views = _first_value(item.get("playCount"), item.get("viewCount"), item.get("views"),
                             stats.get("playCount"), stats.get("viewCount"), stats.get("views"), default=None)
        comments = _first_value(item.get("commentCount"), item.get("comments"),
                                stats.get("commentCount"), stats.get("comments"), default=None)
        shares = _first_value(item.get("shareCount"), item.get("shares"),
                              stats.get("shareCount"), stats.get("shares"), default=None)
        saves = _first_value(item.get("collectCount"), item.get("bookmarkCount"), item.get("bookmarks"),
                             stats.get("collectCount"), stats.get("bookmarks"), default=None)
        for name, value in (("likes", likes), ("views", views), ("comments", comments),
                            ("shares", shares), ("saves", saves)):
            if value is not None:
                try:
                    number = int(str(value).replace(",", "").strip())
                    if name == "likes": likes = max(0, number)
                    elif name == "views": views = max(0, number)
                    elif name == "comments": comments = max(0, number)
                    elif name == "shares": shares = max(0, number)
                    else: saves = max(0, number)
                except (TypeError, ValueError):
                    if name == "likes": likes = None
                    elif name == "views": views = None
                    elif name == "comments": comments = None
                    elif name == "shares": shares = None
                    else: saves = None

        cover = _first_value(
            video_meta.get("coverUrl"), video_meta.get("originalCoverUrl"),
            video.get("cover"), video.get("coverUrl"), video.get("originCover"),
            video.get("dynamicCover"), item.get("cover"), item.get("coverUrl"),
            default=""
        )
        if not cover:
            covers = item.get("covers")
            if isinstance(covers, list) and covers:
                cover = covers[0]
        cover = _normalise_media_url(cover)
        url = _normalise_url(_first_value(item.get("webVideoUrl"), item.get("url"),
                                          item.get("videoUrl"), item.get("shareUrl"),
                                          item.get("postPage"), default=""))
        duration = _first_value(video_meta.get("duration"), video.get("duration"), item.get("duration"), default=None)
        try:
            duration = max(0.0, float(duration)) if duration is not None else None
            if duration is not None and duration.is_integer():
                duration = int(duration)
        except (ValueError, TypeError):
            duration = None
        language = str(_first_value(item.get("textLanguage"), item.get("language"), default="") or "")
        is_ad = _first_value(item.get("isAd"), item.get("isSponsored"), default=None)
        if isinstance(is_ad, str):
            if is_ad.strip().casefold() in {"true", "1", "yes", "y"}:
                is_ad = True
            elif is_ad.strip().casefold() in {"false", "0", "no", "n"}:
                is_ad = False
            else:
                is_ad = None

        result = {
            "id": video_id,
            "desc": desc,
            "autor": str(author_value or ""),
            "likes": likes,
            "fecha": fecha,
            "hashtags": tags,
            "cover": str(cover or ""),
            "url": url,
            "autor_nombre": str(author_name or ""),
            "autor_usuario": str(author_user or ""),
            "views": views,
            "comments": comments,
            "shares": shares,
            "saves": saves,
            "duration": duration,
            "language": language,
            "is_ad": bool(is_ad) if is_ad is not None else None,
        }
        videos.append(result)
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
COSTLOG_PATH = Path(__file__).resolve().parent / "coste_tiktok.jsonl"
_fail_count: dict = {}


def _token() -> str:
    # server_v1 carga .env indirectamente a through de paywall; MCP no importa paywall,
    # so el router debe resolver APIFY_TOKEN por without sin imprimirlo.
    tok = os.environ.get("APIFY_TOKEN", "").strip()
    if tok:
        return tok
    env_file = Path(__file__).resolve().parent.parent / ".env"
    try:
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("APIFY_TOKEN="):
                tok = line.split("=", 1)[1].strip().strip("\"").strip("'")
                if tok:
                    return tok
    except OSError:
        pass
    try:
        return (Path(__file__).resolve().parent.parent / "apify_token.txt").read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def log_coste(actor: str, kind: str, items_n: int, ms: int, ok: bool):
    """Coste estimado a partir del precio público PPR; no sustituye la factura de Apify."""
    request_id = _COST_REQUEST_ID.get()
    rate = _PUBLIC_PPR_USD_PER_1000.get((str(actor), str(kind)))
    rate = rate if rate is not None else None
    if not ok:
        estimated_cost = None
        cost_basis = "failed_run_cost_unknown"
    elif int(items_n or 0) <= 0:
        estimated_cost = None
        cost_basis = "empty_run_cost_unknown"
    elif rate is None:
        estimated_cost = None
        cost_basis = "provider_cost_not_verified"
    else:
        estimated_cost = max(0, int(items_n)) * rate / 1000.0
        cost_basis = "published_starting_price_estimate"
    record = {
        "ts": int(time.time()), "actor": actor, "kind": kind,
        "items": int(items_n or 0), "ms": int(ms or 0), "ok": bool(ok),
        "cost_est_usd": round(estimated_cost, 8) if estimated_cost is not None else None,
        "cost_basis": cost_basis,
        "source_rate_usd_per_1000": rate,
    }
    if request_id:
        record["request_id"] = request_id
    try:
        with open(COSTLOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass



def _run_sync(actor: str, payload: dict, kind: str = "search", timeout_s: int | None = None) -> tuple:
    """Ejecuta un actor con deadline configurable; nunca incluye el token en la URL."""
    tok = _token()
    if not tok:
        return None, "sin APIFY_TOKEN"
    try:
        run_timeout = max(5, min(30, int(timeout_s or SYNC_TIMEOUT_S)))
    except (TypeError, ValueError):
        run_timeout = SYNC_TIMEOUT_S
    url = (f"{APIFY_BASE}/v2/acts/{urllib.parse.quote(actor, safe='~')}/"
           f"run-sync-get-dataset-items?timeout={run_timeout}")
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    started = time.monotonic()
    try:
        req = urllib.request.Request(
            url, data=body,
            headers={"Content-Type": "application/json", "Accept": "application/json",
                     "Authorization": "Bearer " + tok},
        )
        with urllib.request.urlopen(req, timeout=run_timeout + 5) as response:
            items = json.load(response)
        elapsed_ms = int((time.monotonic() - started) * 1000)
        if not isinstance(items, list):
            raise ValueError("dataset_response_not_list")
        log_coste(actor, kind, len(items), elapsed_ms, True)
        _fail_count[actor] = 0
        return items, ""
    except Exception as exc:
        elapsed_ms = int((time.monotonic() - started) * 1000)
        log_coste(actor, kind, 0, elapsed_ms, False)
        _fail_count[actor] = _fail_count.get(actor, 0) + 1
        if isinstance(exc, urllib.error.HTTPError):
            detail = f"HTTP{exc.code}"
        elif isinstance(exc, (TimeoutError, urllib.error.URLError)):
            detail = "timeout_or_network"
        elif isinstance(exc, ValueError):
            detail = "invalid_dataset_response"
        else:
            detail = type(exc).__name__
        return None, detail


def _search_terms(query: str) -> list:
    import re
    import unicodedata
    text = unicodedata.normalize("NFKD", str(query or "").casefold())
    text = "".join(char for char in text if not unicodedata.combining(char))
    stop = {"de", "del", "para", "con", "en", "y", "la", "el", "las", "los", "por",
            "a", "the", "and", "for", "with", "on", "of", "to", "in", "un", "una"}
    return [term for term in re.findall(r"[a-z0-9]+", text) if term not in stop and len(term) > 1]


def _relevance(query: str, video: dict) -> float:
    terms = _search_terms(query)
    if not terms:
        return 0.5
    import unicodedata
    text = str(video.get("desc") or "").casefold()
    tag_text = " ".join(str(tag) for tag in video.get("hashtags", []) or [])
    combined = unicodedata.normalize("NFKD", text + " " + tag_text).casefold()
    combined = "".join(char for char in combined if not unicodedata.combining(char))
    hits = sum(1 for term in terms if term in combined)
    return hits / max(1, len(terms))


def _record_completeness(video: dict) -> int:
    fields = ("id", "desc", "autor", "likes", "fecha", "hashtags", "cover", "url", "views", "comments", "shares")
    return sum(1 for field in fields if video.get(field) not in (None, "", []))


def _rank_videos(query: str, rows: list, max_results: int) -> list:
    """Deduplica por ID, combina los campos no vacíos y clasifica por relevancia."""
    by_id = {}
    for source_row in rows:
        if not isinstance(source_row, dict):
            continue
        row = dict(source_row)
        video_id = str(row.get("id") or "").strip()
        if not video_id:
            continue
        row["relevancia"] = round(_relevance(query, row), 3)
        current = by_id.get(video_id)
        if current is None:
            by_id[video_id] = row
            continue
        # El registro más relevante/completo aporta los valores preferidos; rellenar huecos del otro.
        if (row["relevancia"], _record_completeness(row)) > (
                current.get("relevancia", 0), _record_completeness(current)):
            row, current = current, row
        combined = dict(current)
        for key, value in row.items():
            if combined.get(key) in (None, "", []) and value not in (None, "", []):
                combined[key] = value
        tags = _normalise_tags((combined.get("hashtags") or []) + (row.get("hashtags") or []))
        combined["hashtags"] = tags
        combined["relevancia"] = round(_relevance(query, combined), 3)
        by_id[video_id] = combined

    ranked = list(by_id.values())
    # Stable tie-break: query relevance first, then completeness, then likes; ID final deterministic tie.
    ranked.sort(key=lambda v: (v.get("relevancia", 0), _record_completeness(v),
                               _safe_count(v.get("likes")), str(v.get("id"))), reverse=True)
    return ranked[:max(1, min(50, int(max_results)))]


def _needs_search_fallback(query: str, videos: list, limit: int) -> bool:
    if not videos:
        return True
    # Few results relative to the requested limit usually means a weak search response.
    minimum_expected = 1 if limit == 1 else max(2, min(3, (limit + 3) // 4))
    if len(videos) < minimum_expected:
        return True
    scores = [_relevance(query, video) for video in videos]
    if not scores:
        return True
    match_ratio = sum(1 for score in scores if score >= 0.5) / len(scores)
    average = sum(scores) / len(scores)
    # Important links/media metadata should not disappear silently; a secondary source may fill gaps.
    media_ratio = sum(1 for video in videos if video.get("cover") and video.get("url")) / len(videos)
    core_fields = ("id", "desc", "autor", "likes", "fecha", "hashtags")
    core_ratio = sum(
        sum(1 for field in core_fields if video.get(field) not in (None, "", [])) / len(core_fields)
        for video in videos
    ) / len(videos)
    return (average < 0.45 and match_ratio < 0.5) or media_ratio < 0.5 or core_ratio < 0.65


def _search_status(query: str, videos: list, limit: int) -> str:
    return "ok" if videos else "miss"


def _payload_for_actor(actor: str, query: str, limit: int, kind: str = "search", payload: dict | None = None) -> dict:
    # Actores distintos publican contratos de entrada distintos; adaptar el input al proveedor.
    source = payload or {}
    lowered = actor.lower()
    if kind == "search" and lowered.startswith("apidojo~"):
        return {"keywords": [query], "maxItems": limit, "location": PROXY_COUNTRY,
                "sortType": "RELEVANCE", "dateRange": "DEFAULT", "includeSearchKeywords": True}
    if kind == "perfil" and lowered == "apidojo~tiktok-profile-scraper":
        usernames = source.get("profiles") or source.get("usernames") or [query]
        return {"usernames": usernames, "maxItems": max(10, min(100, limit))}
    if kind == "comments" and lowered == "apidojo~tiktok-comments-scraper":
        urls = source.get("postURLs") or source.get("startUrls") or [query]
        try:
            max_items = max(1, min(50, int(source.get("commentsPerPost", limit))))
        except (TypeError, ValueError):
            max_items = max(1, min(50, int(limit)))
        return {"startUrls": urls, "maxItems": max_items, "includeReplies": False}
    return dict(source) if source else build_search_input(query, limit)


def _call_search_actor(actor: str, payload: dict, query: str, kind: str, deadline: float):
    remaining = deadline - time.monotonic()
    if remaining < 7:
        return None, "search_budget_exhausted"
    timeout = max(5, min(SYNC_TIMEOUT_S, int(remaining - 3)))
    requested = payload.get("resultsPerPage", payload.get("maxItems", 20))
    actor_payload = _payload_for_actor(actor, query, requested, kind=kind, payload=payload)
    items, error = _run_sync(actor, actor_payload, kind=kind, timeout_s=timeout)
    if items is None:
        return None, error
    normalised = normalize_dataset(items).get("videos", [])
    ranked = _rank_videos(query, normalised, 50)
    if not ranked:
        _fail_count[actor] = _fail_count.get(actor, 0) + 1
    return ranked, ""


def run_search(q: str, max_results: int = 20) -> tuple:
    """Busca con deadline global, respaldo por baja calidad y merge/dedupe de fuentes.

    Devuelve ('ok', payload), ('miss', free-miss) o ('retry', 202 sugerido).
    Ningún actorId sale al consumidor y los intentos quedan contabilizados.
    """
    query = " ".join(str(q or "").split())[:200]
    try:
        limit = max(1, min(50, int(max_results)))
    except (TypeError, ValueError):
        limit = 20
    if not query:
        return "invalid", {"error": "q requerido"}
    deadline = time.monotonic() + SEARCH_BUDGET_S
    payload = build_search_input(query, limit)
    primary = ACTOR_FALLBACK if _fail_count.get(ACTOR_SEARCH, 0) >= 3 else ACTOR_SEARCH
    sibling = ACTOR_SEARCH if primary == ACTOR_FALLBACK else ACTOR_FALLBACK
    candidates = [primary, sibling, ACTOR_SEARCH_QUALITY_FALLBACK]
    candidates = list(dict.fromkeys(actor for actor in candidates if actor))
    all_rows = []
    attempts = []
    successful_attempts = 0
    for index, actor in enumerate(candidates):
        if index > 0:
            current = _rank_videos(query, all_rows, limit)
            # Avoid extra provider cost/latency when the first response is already sound.
            if not _needs_search_fallback(query, current, limit):
                break
        rows, error = _call_search_actor(actor, payload, query, "search", deadline)
        attempts.append({"actor_role": "primary" if index == 0 else "fallback",
                         "ok": rows is not None, "error": error or ""})
        if rows is not None:
            successful_attempts += 1
            all_rows.extend(rows)
        if time.monotonic() >= deadline - 2:
            break
    videos = _rank_videos(query, all_rows, limit)
    search_meta = {
        "sources_consulted": len(attempts),
        "fallback_used": len(attempts) > 1,
        "result_count": len(videos),
        "relevance_avg": round(sum(float(video.get("relevancia", 0) or 0) for video in videos) / max(1, len(videos)), 3),
        "cover_coverage": round(sum(bool(video.get("cover")) for video in videos) / max(1, len(videos)), 3),
        "url_coverage": round(sum(bool(video.get("url")) for video in videos) / max(1, len(videos)), 3),
    }
    if videos:
        return "ok", {"videos": videos, "free_miss": False, "search_meta": search_meta}
    if successful_attempts:
        return "miss", {"videos": [], "free_miss": True, "search_meta": search_meta}
    last_error = next((a["error"] for a in reversed(attempts) if a["error"]), "backend_unavailable")
    return "retry", {"retry_hint": "reintenta en 60s", "q": query,
                     "backend_error": last_error, "retry_after_seconds": 60}


def _safe_count(value) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _normalise_username(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if "://" in raw:
        parsed = urllib.parse.urlsplit(raw)
        host = (parsed.hostname or "").lower()
        if host not in {"tiktok.com", "www.tiktok.com", "m.tiktok.com"}:
            return ""
        parts = [segment for segment in parsed.path.split("/") if segment]
        if not parts or not parts[0].startswith("@"):
            return ""
        raw = parts[0].lstrip("@")
    else:
        raw = raw.lstrip("@")
    if not 1 <= len(raw) <= 24 or not all(c.isalnum() or c in "._" for c in raw):
        return ""
    return raw


def run_profile(user: str) -> tuple:
    """Scrape a public profile and up to 10 recent posts. Returns (status, payload)."""
    username = _normalise_username(user)
    if not username:
        return "invalid", {"error": "user invalido: usa un nombre de usuario publico o URL de perfil TikTok"}
    payload = {
        "profiles": [username],
        "resultsPerPage": 10,
        "maxFollowersPerProfile": 0,
        "maxFollowingPerProfile": 0,
        "commentsPerPost": 0,
        "topLevelCommentsPerPost": 0,
        "maxRepliesPerComment": 0,
        "shouldDownloadVideos": False,
        "shouldDownloadCovers": False,
        "shouldDownloadAvatars": False,
        "shouldDownloadSlideshowImages": False,
    }
    items, err = _run_sync(ACTOR_PROFILE, payload, kind="perfil")
    rows = [item for item in (items or []) if isinstance(item, dict) and not item.get("errorCode")] if items is not None else []
    def has_profile_metadata(source_rows):
        for item in source_rows:
            candidate = _first_value(item.get("authorMeta"), item.get("author"), item.get("channel"), default={})
            if not isinstance(candidate, dict):
                continue
            if any(candidate.get(key) not in (None, "", [], {}) for key in (
                "uniqueId", "username", "name", "nickName", "signature", "bio",
                "fans", "followers", "followerCount", "followersCount", "stats",
            )):
                return True
        return False
    profile_has_data = bool(rows) and has_profile_metadata(rows)
    if (items is None or not profile_has_data) and ACTOR_PROFILE_FALLBACK and ACTOR_PROFILE_FALLBACK != ACTOR_PROFILE:
        fallback_payload = _payload_for_actor(
            ACTOR_PROFILE_FALLBACK, username, 10, kind="perfil", payload=payload
        )
        fallback_items, fallback_err = _run_sync(ACTOR_PROFILE_FALLBACK, fallback_payload, kind="perfil")
        if fallback_items is not None:
            # Preserve posts from the primary and fill metadata/posts from the secondary.
            combined = (items or []) + fallback_items if isinstance(items, list) else fallback_items
            items, err = combined, ""
            rows = [item for item in (items or []) if isinstance(item, dict) and not item.get("errorCode")]
        elif items is None:
            err = fallback_err
    if items is None:
        return "retry", {"retry_hint": "reintenta en 60s", "user": username, "backend_error": err}
    posts = [item for item in rows if item.get("id") or item.get("text") or item.get("desc")]
    meta = {}
    for item in rows:
        candidate = _first_value(item.get("authorMeta"), item.get("author"), item.get("channel"), default={})
        if isinstance(candidate, dict) and candidate:
            meta = candidate
            break
    if not posts and not meta:
        return "miss", {
            "user": username, "bio": "", "followers": None, "ultimos": [], "free_miss": True
        }
    video_items = [item for item in posts if item.get("id")]
    videos = normalize_dataset(video_items).get("videos", [])[:10]
    user_out = str(_first_value(meta.get("uniqueId"), meta.get("username"), meta.get("name"), default=username)).lstrip("@")
    bio = str(_first_value(meta.get("signature"), meta.get("bio"), meta.get("description"), default="") or "")
    follower_stats = _as_dict(_first_value(meta.get("stats"), meta.get("authorStats"), default={}))
    followers_raw = _first_value(meta.get("fans"), meta.get("followers"), meta.get("followerCount"),
                                 meta.get("followersCount"), follower_stats.get("followerCount"), default=None)
    followers = _safe_count(followers_raw) if followers_raw is not None else None
    return "ok", {
        "user": user_out or username,
        "bio": bio[:1000],
        "followers": followers,
        "ultimos": videos,
        "free_miss": False,
    }


def _normalise_video_url(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if raw.isdigit() and 8 <= len(raw) <= 25:
        return "https://www.tiktok.com/@/video/" + raw
    if "://" not in raw:
        raw = "https://" + raw
    try:
        parsed = urllib.parse.urlsplit(raw)
    except ValueError:
        return ""
    host = (parsed.hostname or "").lower()
    allowed_hosts = {
        "tiktok.com", "www.tiktok.com", "m.tiktok.com",
        "vm.tiktok.com", "vt.tiktok.com", "t.tiktok.com",
    }
    if host not in allowed_hosts or parsed.scheme.lower() not in {"http", "https"}:
        return ""
    path = parsed.path or "/"
    is_long_video = "/video/" in path or "/share/video/" in path
    is_short_link = host in {"vm.tiktok.com", "vt.tiktok.com", "t.tiktok.com"} and path != "/"
    if not (is_long_video or is_short_link):
        return ""
    # Drop tracking/query parameters; the upstream actor only needs the public TikTok URL.
    return urllib.parse.urlunsplit(("https", host, path, "", ""))


def run_comments(video_id: str, max_comments: int = 50) -> tuple:
    """Scrape public comments and return transparent, non-exhaustive quality metadata."""
    video_url = _normalise_video_url(video_id)
    if not video_url:
        return "invalid", {"error": "id invalido: usa un ID numerico o URL publica de video TikTok"}
    try:
        requested_limit = int(max_comments)
    except (TypeError, ValueError):
        requested_limit = 50
    limit = max(1, min(50, requested_limit))
    payload = {
        "postURLs": [video_url],
        "commentsPerPost": limit,
        "maxRepliesPerComment": 0,
        "resultsPerPage": limit,
    }
    items, err = _run_sync(ACTOR_COMMENTS, payload, kind="comments")
    source_used = "primary"
    duplicate_count = 0

    def extract_comment_rows(source):
        return [
            item for item in (source or [])
            if isinstance(item, dict) and not item.get("errorCode")
            and isinstance(_first_value(item.get("text"), item.get("comment"), item.get("commentText"), default=""), str)
            and _first_value(item.get("text"), item.get("comment"), item.get("commentText"), default="").strip()
        ]

    rows = extract_comment_rows(items)
    if (items is None or not rows) and ACTOR_COMMENTS_FALLBACK and ACTOR_COMMENTS_FALLBACK != ACTOR_COMMENTS:
        fallback_payload = _payload_for_actor(
            ACTOR_COMMENTS_FALLBACK, video_url, limit, kind="comments", payload=payload
        )
        fallback_items, fallback_err = _run_sync(ACTOR_COMMENTS_FALLBACK, fallback_payload, kind="comments")
        if fallback_items is not None:
            items, err, rows = fallback_items, "", extract_comment_rows(fallback_items)
            source_used = "fallback"
        elif items is None:
            err = fallback_err
    if items is None:
        return "retry", {"retry_hint": "reintenta en 60s", "id": str(video_id), "backend_error": err}
    if not rows:
        return "miss", {
            "id": str(video_id), "comments": [], "free_miss": True,
            "comments_meta": _comments_quality_meta([], limit, source_used, 0),
        }

    # Deduplicate only by stable comment ID. Identical text can legitimately be posted by different users.
    selected_rows = []
    seen_comment_ids = set()
    for row in rows:
        comment_id = _first_value(row.get("id"), row.get("commentId"), row.get("cid"), default="")
        if comment_id:
            identity = str(comment_id)
            if identity in seen_comment_ids:
                duplicate_count += 1
                continue
            seen_comment_ids.add(identity)
        selected_rows.append(row)
        if len(selected_rows) >= limit:
            break

    comments = []
    for item in selected_rows:
        user_obj = _as_dict(_first_value(item.get("user"), item.get("authorMeta"), default={}))
        author_value = _first_value(
            item.get("uniqueId"), item.get("username"), user_obj.get("username"),
            user_obj.get("uniqueId"), item.get("author"), default=""
        )
        if isinstance(author_value, dict):
            user_obj = {**author_value, **user_obj}
            author_value = _first_value(user_obj.get("uniqueId"), user_obj.get("username"),
                                        user_obj.get("name"), user_obj.get("nickName"),
                                        user_obj.get("displayName"), default="")
        author_user = str(_first_value(
            item.get("uniqueId"), item.get("username"), user_obj.get("username"),
            user_obj.get("uniqueId"), default=""
        ) or "")
        author_name = str(_first_value(
            user_obj.get("displayName"), user_obj.get("nickname"), user_obj.get("nickName"),
            user_obj.get("name"), default=""
        ) or "")
        author_url = _normalise_url(_first_value(user_obj.get("url"), user_obj.get("profileUrl"), default=""))
        text_value = _first_value(item.get("text"), item.get("comment"), item.get("commentText"), default="")
        likes_raw = _first_value(item.get("diggCount"), item.get("likes"), item.get("likeCount"), default=None)
        replies_raw = _first_value(item.get("replyCount"), item.get("repliesCount"), default=None)
        created_at = _first_value(item.get("createdAt"), item.get("createTimeISO"),
                                   item.get("createTime"), item.get("timestamp"), default="")
        comment_id = _first_value(item.get("id"), item.get("commentId"), item.get("cid"), default="")
        comments.append({
            "id": str(comment_id or ""),
            "autor": author_user or author_name or str(author_value or ""),
            "autor_usuario": author_user,
            "autor_nombre": author_name,
            "autor_url": author_url,
            "texto": str(text_value or "")[:1000],
            "likes": _safe_count(likes_raw) if likes_raw is not None else None,
            "fecha": _normalise_date(created_at),
            "respuestas": _safe_count(replies_raw) if replies_raw is not None else None,
            "idioma": str(_first_value(item.get("commentLanguage"), item.get("language"), default="") or ""),
        })
    return "ok", {
        "id": str(video_id), "comments": comments, "free_miss": False,
        "comments_meta": _comments_quality_meta(comments, limit, source_used, duplicate_count),
    }


def _comments_quality_meta(comments: list, requested_count: int, source_used: str, duplicate_count: int) -> dict:
    """M?tricas observadas; no prometen que TikTok haya expuesto todos los comentarios."""
    count = len(comments)
    fields = {
        "id": lambda c: bool(c.get("id")),
        "autor": lambda c: bool(c.get("autor")),
        "fecha": lambda c: bool(c.get("fecha")),
        "likes": lambda c: c.get("likes") is not None,
        "respuestas": lambda c: c.get("respuestas") is not None,
    }
    coverage = {
        name: round(100 * sum(1 for comment in comments if predicate(comment)) / count, 1) if count else 0.0
        for name, predicate in fields.items()
    }
    return {
        "requested_count": int(requested_count),
        "returned_count": count,
        "unique_id_count": sum(1 for comment in comments if comment.get("id")),
        "duplicate_count": int(duplicate_count),
        "source_used": source_used if source_used in {"primary", "fallback"} else "unknown",
        "field_coverage_pct": coverage,
        "exhaustive": False,
    }


def _canonical_query(q: str) -> str:
    return " ".join(str(q or "").split()).casefold()


def search_cache_key(q: str, max_results: int = 20) -> str:
    try:
        limit = max(1, min(50, int(max_results)))
    except (TypeError, ValueError):
        limit = 20
    return f"tiktok:v2:search:{PROXY_COUNTRY}:{_canonical_query(q)}:{limit}"


def profile_cache_key(user: str) -> str:
    return f"tiktok:v2:perfil:{_normalise_username(user).casefold()}"


def comments_cache_key(video_id: str, max_comments: int = 50) -> str:
    try:
        limit = max(1, min(50, int(max_comments)))
    except (TypeError, ValueError):
        limit = 50
    normal = _normalise_video_url(video_id)
    # IDs and long-form URLs for the same video share one cache entry.
    import re
    match = re.search(r"/video/([0-9]+)", normal)
    identity = match.group(1) if match else normal.casefold()
    return f"tiktok:v2:comments:{identity}:{limit}"


def actor_health() -> dict:
    # switch auto: si top falla 3 seguidas, el router debe preferir fallback (lo lee server_v1).
    return {"top": ACTOR_SEARCH, "top_fails": _fail_count.get(ACTOR_SEARCH, 0),
            "fallback": ACTOR_FALLBACK, "fallback_fails": _fail_count.get(ACTOR_FALLBACK, 0),
            "quality_fallback_configured": bool(ACTOR_SEARCH_QUALITY_FALLBACK),
            "quality_fallback_fails": _fail_count.get(ACTOR_SEARCH_QUALITY_FALLBACK, 0),
            "prefer_fallback": _fail_count.get(ACTOR_SEARCH, 0) >= 3,
            "budget_s": SEARCH_BUDGET_S, "per_actor_timeout_s": SYNC_TIMEOUT_S}
