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


def _hit(bucket: dict, key: str, maximum: int) -> bool:
    now = time.time()
    hits = bucket.setdefault(key, [])
    while hits and hits[0] <= now - _RATE_WINDOW:
        hits.pop(0)
    if len(hits) >= maximum:
        return False
    hits.append(now)
    return True

MOCK_VIDEOS = [
    {"id": "7106686413104970501", "desc": "receta paella valenciana",
     "autor": "@cocina_es", "likes": 152300, "fecha": "2026-09-20",
     "hashtags": ["paella", "receta"], "cover": ""},
]


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


@app.get("/health")
async def health():
    return {"status": "ok", "service": "tiktok-bridge", "version": "1.0.0"}


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
    return {"ventas": ventas, "usdc_cobrado": round(usdc, 2)}


@app.post("/v1/tiktok/search")
async def search(body: dict, request: Request):
    # Orden deliberado: sin firma siempre 402 (el validador CDP y la sonda Bazaar
    # mandan body vacío; un 400 aquí nos desindexa). Solo con firma se valida input.
    if not request.headers.get("PAYMENT-SIGNATURE"):
        return _402(challenge_402(str(request.url), "search", {"videos": MOCK_VIDEOS}))
    q = str((body or {}).get("q", "")).strip()
    if not q:
        return JSONResponse(status_code=400, content={"error": "q requerido"})
    if pw is None:
        return JSONResponse(status_code=502, content={"error": "paywall no configurado"})
    import base64 as _b64
    import json as _json
    import asyncio as _aio
    sig = request.headers.get("PAYMENT-SIGNATURE", "")
    ok, reason = pw.structural_ok(sig, "search")
    if not ok:
        ch = challenge_402(str(request.url), "search", {"videos": MOCK_VIDEOS})
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
        return JSONResponse(status_code=402, content={"error": "pago rechazado",
                                                      "reason": str(ver.get("invalidReason", ver))[:200]})
    try:
        max_results = max(1, min(50, int((body or {}).get("max", 20))))
    except (TypeError, ValueError):
        max_results = 20
    key = f"tiktok:search:{q.lower()}:{max_results}"
    try:
        import cache as _cache
        import tiktok_router as _router
    except ImportError:
        return JSONResponse(status_code=502, content={"error": "router no disponible"})
    hit = await _cache.get(key)
    if hit is not None:
        data = {k: v for k, v in hit.items() if k not in ("cached", "ts", "q")}
        body_out = {"q": q, **data, "cached": True, "ts": int(time.time())}
    else:
        status, data = await _aio.to_thread(_router.run_search, q, max_results)
        if status == "retry":
            return JSONResponse(status_code=202, content=data)
        body_out = {"q": q, **data, "cached": False, "ts": int(time.time())}
        await _cache.put(key, body_out)
    if body_out.get("free_miss"):
        return body_out  # sin resultados no hay settle: no se cobra
    try:
        stl = await _aio.to_thread(pw.facilitator_call_cdp, "/settle", payload, reqs)
    except Exception:
        return JSONResponse(status_code=502, content={"error": "liquidacion indeterminada"})
    if stl.get("success") is False:
        return JSONResponse(status_code=502, content={"error": "settle fallido",
                                                      "reason": str(stl.get("invalidReason", stl))[:200]})
    _rcpt = stl.get("receipt") if isinstance(stl.get("receipt"), dict) else {}
    tx = str(_rcpt.get("transactionHash") or stl.get("txHash") or stl.get("transactionHash")
             or stl.get("transaction") or stl.get("hash") or "")
    try:
        with open("settle_last.json", "w", encoding="utf-8") as _f:
            _f.write(_json.dumps(stl, separators=(",", ":"))[:4000])
    except OSError:
        pass
    _pl = payload.get("payload", payload)
    payer = str((_pl.get("authorization", {}) or {}).get("from", "") or payload.get("authorization", {}).get("from", ""))
    pw.log_venta(payer, tx, "search")
    # Header en shape SettleResponse oficial (el cliente lo valida con pydantic).
    _settle_hdr = {"success": True, "transaction": tx, "network": "eip155:8453",
                   "payer": payer, "amount": "80000"}
    presp = _b64.b64encode(_json.dumps(_settle_hdr).encode()).decode()
    return JSONResponse(body_out, headers={"PAYMENT-RESPONSE": presp})


@app.post("/v1/tiktok/perfil")
async def perfil(body: dict, request: Request):
    if not request.headers.get("PAYMENT-SIGNATURE"):
        return _402(challenge_402(str(request.url), "perfil", {"user": "cocina_es"}))
    user = str((body or {}).get("user", "")).strip()
    if not user:
        return JSONResponse(status_code=400, content={"error": "user requerido"})
    # Backend perfil aún no existe: 501 ANTES de verificar/liquidar (nunca se cobra).
    return JSONResponse(status_code=501, content={"error": "endpoint en construccion: solo /v1/tiktok/search cobra hoy"})


@app.post("/v1/tiktok/comments")
async def comments(body: dict, request: Request):
    if not request.headers.get("PAYMENT-SIGNATURE"):
        return _402(challenge_402(str(request.url), "comments", {"id": "7635981647359380758"}))
    vid = str((body or {}).get("id", "")).strip()
    if not vid:
        return JSONResponse(status_code=400, content={"error": "id requerido"})
    # Backend comments aún no existe: 501 ANTES de verificar/liquidar (nunca se cobra).
    return JSONResponse(status_code=501, content={"error": "endpoint en construccion: solo /v1/tiktok/search cobra hoy"})


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=41243)
