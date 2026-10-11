---
name: tiktok-bridge-search
description: Busca videos públicos de TikTok y devuelve JSON limpio (id, desc, autor, likes, fecha, hashtags, cover). Pago por petición 0.08 USDC en Base mainnet vía x402, sin cuenta ni API key. Free-miss si no hay resultados.
---

# TikTok Bridge — Consultas TikTok para agentes

Puente que sustituye el flujo Apify (cuenta + token + run async + polling + dataset) por 1 fetch con wallet. Solo contenido público. Sin login.

## Búsqueda — x402 en Base mainnet

- **0.08 USDC por petición.** `POST https://veredicto.dpdns.org/v1/tiktok/search`
- Red: Base mainnet, CAIP-2 `eip155:8453`, USDC. Sin suscripción. Nunca compartas claves privadas.

Primero provoca el 402 (sin firma):

```http
POST https://veredicto.dpdns.org/v1/tiktok/search
Content-Type: application/json

{"q": "paella", "max": 20}
```

Responde HTTP 402 con requisitos + ejemplo output + cabecera `PAYMENT-REQUIRED`. Un cliente x402 compatible construye/firma el payload y reintenta el POST con `PAYMENT-SIGNATURE` (base64) y el mismo JSON. Con pago válido: 200 + `videos[]` + cabecera `PAYMENT-RESPONSE`. Sin resultados: 200 con `free_miss:true` sin cargo.

```json
{"q": "paella", "max": 20}
```

Respuesta: `{q, videos: [{id, desc, autor, likes, fecha, hashtags, cover}], cached, ts}`.

## Perfil y comments (en construcción)

- `POST https://veredicto.dpdns.org/v1/tiktok/perfil {"user":"..."}` — 0.08 USDC (hoy 501 sin cargo).
- `POST https://veredicto.dpdns.org/v1/tiktok/comments {"id":"...","max":50}` — 0.05 USDC (hoy 501 sin cargo).

## MCP

- MCP Streamable HTTP: https://veredicto.dpdns.org/tiktok-mcp/mcp
- Tools: `tiktok_search` (router en local), `tiktok_perfil_info`, `tiktok_comments_info` (informativas, no liquidan).
