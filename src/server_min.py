#!/usr/bin/env python3
"""TIKTOK BRIDGE paso 1: contrato fijo con mock real. Sin cobro, sin Apify."""
import time
from fastapi import FastAPI
from fastapi.responses import JSONResponse
import uvicorn

app = FastAPI(title="TikTok Bridge")

MOCK_SEARCH = {
    "videos": [
        {"id": "7106686413104970501", "desc": "receta paella valenciana",
         "autor": "@cocina_es", "likes": 152300, "fecha": "2026-09-20",
         "hashtags": ["paella", "receta"], "cover": ""},
        {"id": "7106686413104970502", "desc": "paella en 60 segundos",
         "autor": "@foodtiktok", "likes": 89300, "fecha": "2026-09-22",
         "hashtags": ["paella"], "cover": ""},
    ],
    "cached": True, "ts": int(time.time()),
}

MOCK_PERFIL = {
    "user": "cocina_es", "bio": "Recetas ES", "followers": 450000,
    "ultimos": MOCK_SEARCH["videos"],
}

MOCK_COMMENTS = {
    "id": "7106686413104970501",
    "comments": [
        {"autor": "@fan1", "texto": "la mejor paella", "likes": 1200},
        {"autor": "@fan2", "texto": "receta?", "likes": 300},
    ],
}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "tiktok-bridge", "version": "0.1.0-mock"}


@app.post("/tiktok/search")
async def search(body: dict):
    q = str(body.get("q", "")).strip()
    if not q:
        return JSONResponse(status_code=400, content={"error": "q requerido"})
    # paso 1: mock. paso 3: router Apify + caché aquí.
    return {"q": q, **MOCK_SEARCH, "price": "0.08 USDC (pendiente paywall paso 2)"}


@app.post("/tiktok/perfil")
async def perfil(body: dict):
    user = str(body.get("user", "")).strip()
    if not user:
        return JSONResponse(status_code=400, content={"error": "user requerido"})
    return {"user": user, **MOCK_PERFIL}


@app.post("/tiktok/comments")
async def comments(body: dict):
    vid = str(body.get("id", "")).strip()
    if not vid:
        return JSONResponse(status_code=400, content={"error": "id requerido"})
    return {"id": vid, **MOCK_COMMENTS}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=41243)
