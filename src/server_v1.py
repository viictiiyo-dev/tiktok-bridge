#!/usr/bin/env python3
"""TIKTOK BRIDGE /v1 — contrato fijo (task 1.1/1.2). Paywall real en task 2."""
import time
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn

try:
    import paywall as pw
    PRICE = pw.PRICE_LABEL
except ImportError:  # fixtures sin paywall
    pw = None
    PRICE = {"search": "0.08 USDC", "perfil": "0.08 USDC", "comments": "0.05 USDC"}

app = FastAPI(title="TikTok Bridge", version="1.0.0")

import os as _os
STATS_TOKEN = _os.environ.get("STATS_TOKEN", "")

# task 5.1: límites en memoria (sin dependencia nueva; slowapi evaluado, overkill).
# 30/min por IP global, 60/min por wallet compradora. /health exento.
_RATE_IP: dict = {}
_RATE_WALLET: dict = {}
_RATE_WINDOW = 60.0
_RATE_MAX_KEYS = 5000
_RATE_SWEEP_INTERVAL = 15.0
_RATE_LAST_SWEEP = 0.0


def _prune_rate_bucket(bucket: dict, cutoff: float) -> None:
    for bucket_key, timestamps in list(bucket.items()):
        while timestamps and timestamps[0] <= cutoff:
            timestamps.pop(0)
        if not timestamps:
            bucket.pop(bucket_key, None)
    # Memory stays bounded even during a flood of unique IPs or wallet values.
    while len(bucket) > _RATE_MAX_KEYS:
        bucket.pop(next(iter(bucket)), None)


def _hit(bucket: dict, key: str, maximum: int) -> bool:
    global _RATE_LAST_SWEEP
    now = time.monotonic()
    if now - _RATE_LAST_SWEEP >= _RATE_SWEEP_INTERVAL:
        cutoff = now - _RATE_WINDOW
        _prune_rate_bucket(_RATE_IP, cutoff)
        _prune_rate_bucket(_RATE_WALLET, cutoff)
        _RATE_LAST_SWEEP = now
    hits = bucket.get(key)
    if hits is None:
        if len(bucket) >= _RATE_MAX_KEYS:
            bucket.pop(next(iter(bucket)), None)
        hits = []
        bucket[key] = hits
    while hits and hits[0] <= now - _RATE_WINDOW:
        hits.pop(0)
    if len(hits) >= maximum:
        return False
    hits.append(now)
    return True

MOCK_VIDEOS = [
    {"id": "7106686413104970501", "desc": "receta paella valenciana",
     "autor": "@cocina_es", "likes": 152300, "fecha": "2026-09-20T00:00:00Z",
     "hashtags": ["paella", "receta"], "cover": "", "url": "",
     "autor_nombre": None, "autor_usuario": "cocina_es",
     "views": None, "comments": None, "shares": None, "saves": None,
     "duration": None, "language": "", "is_ad": None, "relevancia": 1.0},
]
MOCK_SEARCH_META = {
    "sources_consulted": 1, "fallback_used": False, "result_count": 1,
    "relevance_avg": 1.0, "cover_coverage": 0.0, "url_coverage": 0.0,
}


def _search_example(query: str = "paella") -> dict:
    # Valores ilustrativos para documentar el contrato; no son datos consultados en esta petición.
    return {
        "q": query or "paella", "videos": MOCK_VIDEOS,
        "search_meta": MOCK_SEARCH_META, "free_miss": False,
        "cached": False, "ts": 0, "example_note": "Ejemplo de esquema; no es una consulta real.",
    }


@app.middleware("http")
async def quota_por_ip(request: Request, call_next):
    if request.url.path != "/health":
        ip = request.client.host if request.client else "?"
        if not _hit(_RATE_IP, ip, 30):
            return JSONResponse(status_code=429, content={"error": "Demasiadas peticiones, reintenta en un minuto"})
        # Clave por payer address (el nonce cambia en cada pago; sig[:40] nunca repetiría
        # y el límite jamás saltaría). Best-effort: si no decodifica, cae a prefijo de firma.
        wallet = ""
        _sig = request.headers.get("PAYMENT-SIGNATURE") or ""
        if _sig:
            try:
                import base64 as _b64w
                import json as _jsonw
                _p = _jsonw.loads(_b64w.b64decode(_sig).decode("utf-8"))
                _pay = _p.get("payload", _p)
                wallet = ((_pay.get("authorization", {}) or {}).get("from", "") or _sig[:40])
            except Exception:
                wallet = _sig[:40]
        if wallet and not _hit(_RATE_WALLET, wallet, 60):
            return JSONResponse(status_code=429, content={"error": "Wallet limitada, reintenta en un minuto"})
    return await call_next(request)


def challenge_402(url: str, kind: str, example: dict) -> dict:
    if pw is not None:
        return pw.challenge(url, kind, example)
    return {
        "x402Version": 2, "error": "Payment required",
        "resource": {"url": url, "description": f"TikTok {kind} para agentes. SOLO PUBLICO. Free-miss si 0 resultados.",
                     "mimeType": "application/json", "serviceName": "TikTok Bridge"},
        "accepts": [{"scheme": "exact", "network": "eip155:8453", "amount": "80000",
                     "asset": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
                     "payTo": "PENDIENTE_TASK2", "maxTimeoutSeconds": 60}],
        "price": PRICE[kind], "output": {"example": example},
        "how": "Repite este POST con PAYMENT-SIGNATURE (task 2 activa el cobro real).",
    }


def _402(ch: dict) -> JSONResponse:
    # Spec x402 v2: el cliente oficial solo lee el header PAYMENT-REQUIRED, no el body.
    import base64 as _b
    import json as _j
    return JSONResponse(status_code=402, content=ch,
                        headers={"PAYMENT-REQUIRED": _b.b64encode(_j.dumps(ch).encode()).decode()})


METRICS_PATH = Path(_os.environ.get(
    "METRICS_PATH", str(Path(__file__).resolve().parent / "metrics_tiktok.jsonl")
))


def _record_api_metric(event: str, endpoint: str, status_code: int, latency_ms: int):
    """Métricas agregables sin almacenar IP, wallet, query, cuerpo ni firma."""
    try:
        record = {
            "ts": int(time.time()), "event": event, "endpoint": endpoint,
            "status_code": int(status_code), "latency_ms": max(0, int(latency_ms)),
        }
        METRICS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(METRICS_PATH, "a", encoding="utf-8") as f:
            import json as _json_metrics
            f.write(_json_metrics.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass


@app.middleware("http")
async def request_metrics(request: Request, call_next):
    path = request.url.path
    if not path.startswith("/v1/tiktok/"):
        return await call_next(request)
    started = time.monotonic()
    response = await call_next(request)
    latency_ms = int((time.monotonic() - started) * 1000)
    signed = bool(request.headers.get("PAYMENT-SIGNATURE"))
    code = response.status_code
    if code == 402:
        event = "payment_rejected" if signed else "payment_challenge"
    elif code == 202:
        event = "pending_or_retry"
    elif code == 429:
        event = "rate_limited"
    elif code == 400:
        event = "invalid_request"
    elif code >= 500:
        event = "server_error"
    elif code == 200:
        event = "http_200"
    else:
        event = "other_response"
    _record_api_metric(event, path, code, latency_ms)
    return response


@app.get("/health")
async def health():
    cache_status = {"backend": "unknown"}
    try:
        import cache as _cache
        cache_status = await _cache.backend_status()
    except Exception as exc:
        cache_status = {"backend": "unavailable", "warning": type(exc).__name__}
    base_pay_to = _os.environ.get("X402_PAY_TO_BASE", "").strip().lower()
    tiktok_pay_to = _os.environ.get("X402_PAY_TO_TIKTOK", "").strip().lower()
    recipients_separate = bool(base_pay_to and tiktok_pay_to and base_pay_to != tiktok_pay_to)
    # Sanitized scraper diagnostics: never expose provider actor IDs or credentials on public health.
    scraper_status = {
        "apify_configured": False,
        "search_budget_seconds": None,
        "per_actor_timeout_seconds": None,
        "primary_failures": 0,
        "fallback_failures": 0,
        "quality_fallback_failures": 0,
        "prefer_fallback": False,
        "profile_fallback_configured": False,
        "comments_fallback_configured": False,
    }
    try:
        import tiktok_router as _router
        _router_health = _router.actor_health()
        scraper_status.update({
            "apify_configured": bool(_router._token()),
            "search_budget_seconds": _router_health.get("budget_s"),
            "per_actor_timeout_seconds": _router_health.get("per_actor_timeout_s"),
            "primary_failures": int(_router_health.get("top_fails", 0)),
            "fallback_failures": int(_router_health.get("fallback_fails", 0)),
            "quality_fallback_failures": int(_router_health.get("quality_fallback_fails", 0)),
            "prefer_fallback": bool(_router_health.get("prefer_fallback", False)),
            "profile_fallback_configured": bool(_router.ACTOR_PROFILE_FALLBACK),
            "comments_fallback_configured": bool(_router.ACTOR_COMMENTS_FALLBACK),
        })
    except Exception:
        scraper_status["diagnostic_error"] = "unavailable"
    return {
        "status": "ok", "service": "tiktok-bridge", "version": "1.0.0",
        "cache": cache_status,
        "scraper": scraper_status,
        "payment_config": {
            "tiktok_recipient_configured": bool(tiktok_pay_to),
            "recipient_separate_from_base": recipients_separate,
        },
    }


@app.get("/llms.txt")
async def llms():
    from fastapi.responses import PlainTextResponse
    try:
        txt = Path(__file__).resolve().parent.parent.joinpath("llms.txt").read_text(encoding="utf-8")
    except Exception:
        txt = "TikTok Bridge. POST /v1/tiktok/search {q,max}. POST /v1/tiktok/perfil {user}. POST /v1/tiktok/comments {id,max}. Solo publico. Free-miss si 0."
    return PlainTextResponse(txt, media_type="text/plain")


@app.get("/tiktok/llms.txt", include_in_schema=False, operation_id="tiktok_llms_pub")
async def llms_pub():
    return await llms()


@app.get("/skill.md")
async def skill_md():
    from fastapi.responses import PlainTextResponse
    try:
        txt = Path(__file__).resolve().parent.parent.joinpath("SKILL.md").read_text(encoding="utf-8")
    except Exception:
        txt = "# TikTok Bridge\nPOST /v1/tiktok/search {q} → {videos:[{id,desc,autor,likes,fecha}]}.\n"
    return PlainTextResponse(txt, media_type="text/markdown")


@app.get("/tiktok/skill.md", include_in_schema=False, operation_id="tiktok_skill_pub")
async def skill_pub():
    return await skill_md()


@app.get("/tiktok/agent-card.json", include_in_schema=False, operation_id="tiktok_agent_card_pub")
async def agent_card_pub():
    try:
        txt = Path(__file__).resolve().parent.parent.joinpath("agent-card.json").read_text(encoding="utf-8")
    except Exception:
        txt = "{}"
    from fastapi.responses import Response
    return Response(content=txt, media_type="application/json")


@app.get("/robots.txt")
async def robots():
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse("User-agent: *\nAllow: /\n")


@app.get("/terms", include_in_schema=False)
async def terms():
    from fastapi.responses import HTMLResponse
    return HTMLResponse(
        "<!doctype html><html lang='es'><head><meta charset='utf-8'>"
        "<title>TikTok Bridge - Condiciones</title></head>"
        "<body style='font-family:sans-serif;max-width:640px;margin:40px auto;padding:0 16px'>"
        "<h1>Condiciones</h1>"
        "<p>Puente de consulta TikTok <b>SOLO PUBLICO</b> (search, perfil, comments). "
        "Sin login, sin contenido privado, sin bypass de paywalls. "
        "Cobro por llamada vía x402 en Base mainnet (0.08/0.08/0.05 USDC), sin suscripciones. "
        "Free-miss: sin resultados no hay settle. Solo metadata + cover URL, sin re-host de video.</p>"
        "</body></html>")


@app.get("/tiktok/terms", include_in_schema=False, operation_id="tiktok_terms_pub")
async def terms_pub():
    return await terms()


@app.get("/sitemap.xml", include_in_schema=False)
async def sitemap():
    from fastapi.responses import Response
    return Response(content="""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>/v1/tiktok/search</loc></url>
  <url><loc>/terms</loc></url>
  <url><loc>/skill.md</loc></url>
  <url><loc>/llms.txt</loc></url>
</urlset>""", media_type="application/xml")


@app.get("/stats")
async def stats(request: Request):
    if not STATS_TOKEN or request.headers.get("x-stats-token") != STATS_TOKEN:
        return JSONResponse(status_code=403, content={"error": "Forbidden"})
    ventas = usdc = 0
    try:
        import json as _json
        _sales = str(pw.SALES_PATH) if pw is not None else "ventas_tiktok.jsonl"
        with open(_sales, encoding="utf-8") as f:
            for line in f:
                try:
                    r = _json.loads(line)
                    if r.get("settled_by_facilitator") is True:
                        ventas += 1
                        usdc += int(r.get("amount", 0)) / 1e6
                except Exception:
                    pass
    except FileNotFoundError:
        pass
    events = {}
    try:
        import json as _json
        metric_path = METRICS_PATH
        now = int(time.time())
        with open(metric_path, encoding="utf-8") as f:
            for line in f:
                try:
                    event = _json.loads(line)
                    if now - int(event.get("ts", 0)) <= 30 * 86400:
                        endpoint = str(event.get("endpoint", "unknown"))
                        kind = str(event.get("event", "unknown"))
                        key = endpoint + "|" + kind
                        events[key] = events.get(key, 0) + 1
                except Exception:
                    continue
    except OSError:
        pass
    return {
        "ventas": ventas,
        "usdc_cobrado": round(usdc, 6),
        "metricas_30_dias": events,
        "nota_metricas": "Métricas HTTP por ruta/estado sin IP, consulta, wallet ni firma; http_200 no equivale necesariamente a un pago.",
    }


@app.post("/v1/tiktok/search")
async def search(body: dict, request: Request):
    # Orden deliberado: sin firma siempre 402, incluido el body vac?o de validadores.
    if not request.headers.get("PAYMENT-SIGNATURE"):
        query_example = str((body or {}).get("q", "paella") or "paella").strip()[:200]
        return _402(challenge_402(str(request.url), "search", _search_example(query_example)))
    q = str((body or {}).get("q", "")).strip()
    if not q:
        return JSONResponse(status_code=400, content={"error": "q requerido"})
    try:
        max_results = int((body or {}).get("max", 20))
    except (TypeError, ValueError):
        return JSONResponse(status_code=400, content={"error": "max debe ser un entero entre 1 y 20"})
    if not 1 <= max_results <= 20:
        return JSONResponse(status_code=400, content={
            "error": "max debe estar entre 1 y 20 al precio actual de 0.08 USDC"
        })
    if pw is None:
        return JSONResponse(status_code=502, content={"error": "paywall no configurado"})
    import base64 as _b64
    import json as _json
    import asyncio as _aio

    sig = request.headers.get("PAYMENT-SIGNATURE", "")
    ok, reason = pw.structural_ok(sig, "search")
    if not ok:
        ch = challenge_402(
            str(request.url), "search",
            _search_example(str((body or {}).get("q", "paella") or "paella").strip()[:200])
        )
        ch["reason"] = reason
        return _402(ch)
    try:
        payload = _json.loads(_b64.b64decode(sig).decode("utf-8"))
    except Exception:
        return JSONResponse(status_code=402, content={"error": "payload ilegible"})
    reqs = pw.methods("search")[0]
    try:
        ver = await _aio.to_thread(pw.facilitator_call_cdp, "/verify", payload, reqs)
    except Exception:
        return JSONResponse(status_code=502, content={"error": "facilitador no disponible"})
    if not (ver.get("isValid") or ver.get("success")):
        return JSONResponse(status_code=402, content={
            "error": "pago rechazado",
            "reason": str(ver.get("invalidReason", ver))[:200],
        })

    # Reserva durable y at?mica despu?s de verificar y ANTES de ejecutar cualquier settle.
    # La firma id?ntica, incluso tras reiniciar el proceso, solo puede liquidarse una vez.
    try:
        payment_key, payment_state, saved = pw.begin_payment_request(sig)
    except Exception:
        return JSONResponse(status_code=503, content={
            "error": "almac?n de idempotencia no disponible; no se ha liquidado el pago"
        })
    if payment_state in ("completed", "failed") and saved:
        headers = {"X-Idempotent-Replay": "true"}
        if saved.get("payment_response"):
            headers["PAYMENT-RESPONSE"] = saved["payment_response"]
        return JSONResponse(
            status_code=saved.get("status_code", 200),
            content=saved.get("response_body") or {"error": "respuesta idempotente no disponible"},
            headers=headers,
        )
    if payment_state in ("processing", "settling", "settle_unknown"):
        message = (
            "Liquidaci?n previa indeterminada; no se repetir? autom?ticamente"
            if payment_state in ("settling", "settle_unknown")
            else "Esta firma ya est? siendo procesada"
        )
        return JSONResponse(
            status_code=202, content={"error": message, "retry_after_seconds": 60},
            headers={"Retry-After": "60"},
        )
    if payment_state != "new":
        return JSONResponse(status_code=503, content={"error": "estado de pago no recuperable"})

    try:
        import cache as _cache
        import tiktok_router as _router
    except ImportError:
        pw.release_payment_request(payment_key)
        return JSONResponse(status_code=502, content={"error": "router no disponible"})

    key = _router.search_cache_key(q, max_results)
    try:
        hit = await _cache.get(key)
        if hit is not None:
            data = {k: v for k, v in hit.items() if k not in ("cached", "ts", "q")}
            body_out = {"q": q, **data, "cached": True, "ts": int(time.time())}
        else:
            cost_context = _router.set_cost_request_id(payment_key)
            try:
                status, data = await _aio.to_thread(_router.run_search, q, max_results)
            finally:
                _router.reset_cost_request_id(cost_context)
            if status == "retry":
                pw.release_payment_request(payment_key)
                return JSONResponse(status_code=202, content=data, headers={"Retry-After": "60"})
            body_out = {"q": q, **data, "cached": False, "ts": int(time.time())}
            if body_out.get("free_miss"):
                await _cache.put(key, body_out, ttl=300)
            else:
                await _cache.put(key, body_out)
    except Exception:
        pw.release_payment_request(payment_key)
        return JSONResponse(status_code=502, content={"error": "fallo al consultar TikTok"})

    if body_out.get("free_miss"):
        # Free-miss es resultado terminal, pero no debe liquidar ni volver a ejecutar el scraper.
        try:
            pw.complete_payment_request(payment_key, body_out)
        except Exception:
            return JSONResponse(status_code=503, content={"error": "no se pudo guardar la respuesta idempotente"})
        _record_api_metric("free_miss", "/v1/tiktok/search", 200, 0)
        return body_out

    # Persistir 'settling' antes del POST a CDP. Si hay timeout, el reintento queda bloqueado
    # para conciliaci?n: es preferible revisar un caso dudoso a cobrar dos veces.
    try:
        pw.mark_payment_request_state(payment_key, "settling", response_body=body_out)
    except Exception:
        return JSONResponse(status_code=503, content={
            "error": "no se pudo reservar la liquidaci?n; no se ha llamado a settle"
        })
    try:
        stl = await _aio.to_thread(pw.facilitator_call_cdp, "/settle", payload, reqs)
    except Exception:
        try:
            pw.mark_payment_request_state(
                payment_key, "settle_unknown", response_body=body_out,
                error="timeout o error de transporte al facilitador"
            )
        except Exception:
            pass
        return JSONResponse(status_code=202, content={
            "error": "resultado de liquidaci?n indeterminado; se bloquea el reintento autom?tico",
            "retry_after_seconds": 60,
        }, headers={"Retry-After": "60"})
    if stl.get("success") is False:
        _record_api_metric("payment_settle_failed", "/v1/tiktok/search", 502, 0)
        failure = {
            "error": "settle fallido",
            "reason": str(stl.get("invalidReason", stl))[:200],
        }
        try:
            pw.fail_payment_request(payment_key, failure, status_code=502)
        except Exception:
            pass
        return JSONResponse(status_code=502, content=failure)

    _rcpt = stl.get("receipt") if isinstance(stl.get("receipt"), dict) else {}
    tx = str(_rcpt.get("transactionHash") or stl.get("txHash") or stl.get("transactionHash")
             or stl.get("transaction") or stl.get("hash") or "")
    try:
        _audit = str(Path(pw.SALES_PATH).parent / "settle_last.json")
        with open(_audit, "w", encoding="utf-8") as _f:
            _f.write(_json.dumps({"settle": stl, "bazaar": pw.bazaar_status()},
                                 separators=(",", ":"))[:4000])
    except OSError:
        pass
    _pl = payload.get("payload", payload)
    _authorization = _pl.get("authorization", {}) if isinstance(_pl, dict) else {}
    payer = str((_authorization or {}).get("from", "") or "")
    pw.log_venta(
        payer, tx, "search", request_id=payment_key,
        cache_hit=bool(body_out.get("cached")),
        result_count=len(body_out.get("videos") or []),
    )
    settle_hdr = {
        "success": True, "transaction": tx, "network": "eip155:8453",
        "payer": payer, "amount": "80000",
    }
    presp = _b64.b64encode(_json.dumps(settle_hdr).encode()).decode()
    try:
        pw.complete_payment_request(payment_key, body_out, presp)
    except Exception:
        # El estado persistido 'settling' seguir? bloqueando otro settle si falla SQLite.
        return JSONResponse(status_code=202, content={
            "error": "pago procesado pero no se pudo guardar la respuesta; requiere conciliaci?n",
            "transaction": tx or None,
        }, headers={"Retry-After": "60"})
    _record_api_metric("payment_completed", "/v1/tiktok/search", 200, 0)
    return JSONResponse(body_out, headers={"PAYMENT-RESPONSE": presp})


async def _paid_lookup(
    kind: str, body: dict, request: Request, input_field: str, input_value: str,
    cache_key: str, runner, example: dict
):
    """Common paid flow for profile/comments, with durable signature idempotency."""
    sig = request.headers.get("PAYMENT-SIGNATURE", "")
    if not sig:
        # 402-first is intentional: the catalog validator also sends an empty body.
        return _402(challenge_402(str(request.url), kind, example))
    value = str(input_value or "").strip()
    if not value:
        return JSONResponse(status_code=400, content={"error": f"{input_field} requerido"})
    if pw is None:
        return JSONResponse(status_code=502, content={"error": "paywall no configurado"})

    import asyncio as _aio
    import base64 as _b64
    import json as _json

    ok, reason = pw.structural_ok(sig, kind)
    if not ok:
        challenge = challenge_402(str(request.url), kind, example)
        challenge["reason"] = reason
        return _402(challenge)
    try:
        payload = _json.loads(_b64.b64decode(sig).decode("utf-8"))
    except Exception:
        return JSONResponse(status_code=402, content={"error": "payload ilegible"})
    requirements = pw.methods(kind)[0]
    try:
        verified = await _aio.to_thread(pw.facilitator_call_cdp, "/verify", payload, requirements)
    except Exception:
        return JSONResponse(status_code=502, content={"error": "facilitador no disponible"})
    if not (verified.get("isValid") or verified.get("success")):
        return JSONResponse(status_code=402, content={
            "error": "pago rechazado",
            "reason": str(verified.get("invalidReason", verified))[:200],
        })

    try:
        payment_key, payment_state, saved = pw.begin_payment_request(sig)
    except Exception:
        return JSONResponse(status_code=503, content={
            "error": "almacen de idempotencia no disponible; no se ha liquidado el pago"
        })
    if payment_state in ("completed", "failed") and saved:
        headers = {"X-Idempotent-Replay": "true"}
        if saved.get("payment_response"):
            headers["PAYMENT-RESPONSE"] = saved["payment_response"]
        return JSONResponse(
            status_code=saved.get("status_code", 200),
            content=saved.get("response_body") or {"error": "respuesta idempotente no disponible"},
            headers=headers,
        )
    if payment_state in ("processing", "settling", "settle_unknown"):
        message = (
            "Liquidacion previa indeterminada; no se repetira automaticamente"
            if payment_state in ("settling", "settle_unknown")
            else "Esta firma ya esta siendo procesada"
        )
        return JSONResponse(
            status_code=202, content={"error": message, "retry_after_seconds": 60},
            headers={"Retry-After": "60"},
        )
    if payment_state != "new":
        return JSONResponse(status_code=503, content={"error": "estado de pago no recuperable"})

    try:
        import cache as _cache
    except ImportError:
        pw.release_payment_request(payment_key)
        return JSONResponse(status_code=502, content={"error": "cache no disponible"})
    try:
        hit = await _cache.get(cache_key)
        if hit is not None:
            data = {k: v for k, v in hit.items() if k not in ("cached", "ts", input_field)}
            body_out = {input_field: value, **data, "cached": True, "ts": int(time.time())}
        else:
            cost_context = None
            cost_router = None
            try:
                import tiktok_router as cost_router
                cost_context = cost_router.set_cost_request_id(payment_key)
            except Exception:
                cost_context = None
                cost_router = None
            try:
                status, data = await _aio.to_thread(runner)
            finally:
                if cost_context is not None and cost_router is not None:
                    cost_router.reset_cost_request_id(cost_context)
            if status == "retry":
                pw.release_payment_request(payment_key)
                return JSONResponse(status_code=202, content=data, headers={"Retry-After": "60"})
            if status == "invalid":
                pw.release_payment_request(payment_key)
                return JSONResponse(status_code=400, content=data)
            body_out = {input_field: value, **data, "cached": False, "ts": int(time.time())}
            if body_out.get("free_miss"):
                await _cache.put(cache_key, body_out, ttl=300)
            else:
                await _cache.put(cache_key, body_out)
    except Exception:
        pw.release_payment_request(payment_key)
        return JSONResponse(status_code=502, content={"error": "fallo al consultar TikTok"})

    if body_out.get("free_miss"):
        try:
            pw.complete_payment_request(payment_key, body_out)
        except Exception:
            return JSONResponse(status_code=503, content={"error": "no se pudo guardar la respuesta idempotente"})
        _record_api_metric("free_miss", request.url.path, 200, 0)
        return body_out

    try:
        pw.mark_payment_request_state(payment_key, "settling", response_body=body_out)
    except Exception:
        return JSONResponse(status_code=503, content={
            "error": "no se pudo reservar la liquidacion; no se ha llamado a settle"
        })
    try:
        settled = await _aio.to_thread(pw.facilitator_call_cdp, "/settle", payload, requirements)
    except Exception:
        try:
            pw.mark_payment_request_state(
                payment_key, "settle_unknown", response_body=body_out,
                error="timeout o error de transporte al facilitador"
            )
        except Exception:
            pass
        return JSONResponse(status_code=202, content={
            "error": "resultado de liquidacion indeterminado; se bloquea el reintento automatico",
            "retry_after_seconds": 60,
        }, headers={"Retry-After": "60"})
    if settled.get("success") is False:
        _record_api_metric("payment_settle_failed", request.url.path, 502, 0)
        failure = {"error": "settle fallido", "reason": str(settled.get("invalidReason", settled))[:200]}
        try:
            pw.fail_payment_request(payment_key, failure, status_code=502)
        except Exception:
            pass
        return JSONResponse(status_code=502, content=failure)

    receipt = settled.get("receipt") if isinstance(settled.get("receipt"), dict) else {}
    tx = str(receipt.get("transactionHash") or settled.get("txHash") or settled.get("transactionHash")
             or settled.get("transaction") or settled.get("hash") or "")
    try:
        audit_path = Path(pw.SALES_PATH).parent / "settle_last.json"
        audit_path.write_text(_json.dumps(
            {"kind": kind, "settle": settled, "bazaar": pw.bazaar_status()},
            separators=(",", ":")
        )[:4000], encoding="utf-8")
    except OSError:
        pass
    payment_payload = payload.get("payload", payload)
    authorization = payment_payload.get("authorization", {}) if isinstance(payment_payload, dict) else {}
    payer = str(authorization.get("from", "") or "") if isinstance(authorization, dict) else ""
    if kind == "comments":
        result_count = len(body_out.get("comments") or [])
    elif kind == "perfil":
        result_count = len(body_out.get("ultimos") or [])
    else:
        result_count = 0
    pw.log_venta(
        payer, tx, kind, request_id=payment_key,
        cache_hit=bool(body_out.get("cached")), result_count=result_count,
    )
    settle_header = {
        "success": True, "transaction": tx, "network": "eip155:8453",
        "payer": payer, "amount": pw.PRICE[kind],
    }
    payment_response = _b64.b64encode(_json.dumps(settle_header).encode()).decode()
    try:
        pw.complete_payment_request(payment_key, body_out, payment_response)
    except Exception:
        return JSONResponse(status_code=202, content={
            "error": "pago procesado pero no se pudo guardar la respuesta; requiere conciliacion",
            "transaction": tx or None,
        }, headers={"Retry-After": "60"})
    _record_api_metric("payment_completed", request.url.path, 200, 0)
    return JSONResponse(body_out, headers={"PAYMENT-RESPONSE": payment_response})


@app.post("/v1/tiktok/perfil")
async def perfil(body: dict, request: Request):
    user = str((body or {}).get("user", "")).strip()
    try:
        import tiktok_router as _router
    except ImportError:
        _router = None
    cache_key = _router.profile_cache_key(user) if _router else f"tiktok:v2:perfil:{user.strip().lstrip(chr(64)).casefold()}"
    runner = (lambda: _router.run_profile(user)) if _router else (lambda: ("retry", {"retry_hint": "router no disponible"}))
    return await _paid_lookup(
        "perfil", body, request, "user", user, cache_key, runner,
        {"user": user or "cocina_es", "bio": "", "followers": None,
         "ultimos": MOCK_VIDEOS, "free_miss": False, "cached": False, "ts": 0,
         "example_note": "Ejemplo de esquema; no es una consulta real."},
    )


@app.post("/v1/tiktok/comments")
async def comments(body: dict, request: Request):
    video_id = str((body or {}).get("id", "")).strip()
    try:
        max_comments = max(1, min(50, int((body or {}).get("max", 50))))
    except (TypeError, ValueError):
        max_comments = 50
    try:
        import tiktok_router as _router
    except ImportError:
        _router = None
    cache_key = _router.comments_cache_key(video_id, max_comments) if _router else f"tiktok:v2:comments:{video_id}:{max_comments}"
    runner = (
        lambda: _router.run_comments(video_id, max_comments)
    ) if _router else (lambda: ("retry", {"retry_hint": "router no disponible"}))
    return await _paid_lookup(
        "comments", body, request, "id", video_id, cache_key, runner,
        {"id": video_id or "7635981647359380758",
         "comments": [{"id": "", "autor": "example", "autor_usuario": "",
                       "autor_nombre": "", "autor_url": "", "texto": "comentario publico",
                       "likes": None, "fecha": "", "respuestas": None, "idioma": ""}],
         "free_miss": False, "cached": False, "ts": 0,
         "example_note": "Ejemplo de esquema; no es una consulta real."},
    )


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=41243)
