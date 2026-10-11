# Brief: tiktok-bridge

## Problem
Los agentes IA quieren consultar TikTok (search, perfil, comments) y fallan ~85-95% sin infra: captcha, firma cambiante, rate-limit por IP, API oficial solo académica (4 semanas aprobación, 1000/día, prohibido comercial). Apify lo resuelve con 2661 actors pero exige cuenta + token + run async + polling + dataset + tarjeta. Fricción 6 pasos para 1 consulta.

## Current State
Existe `src/server_min.py` (mock contrato 3 rutas en 41243, compile OK) y `src/tiktok_router.py` (normalización + free-miss + precios). Existe el stack probado de AGENTE COMPARADOR (paywall x402 Base/CDP, MCP/A2A, Caddy). No hay router Apify real, ni paywall, ni caché, ni discovery Bazaar. Carpeta cc-sdd clonada + skills OpenCode instaladas (36 skills), sin specs ni steering: greenfield.

## Desired Outcome
Puente x402 `POST /tiktok/search|perfil|comments` que con 1 fetch + wallet devuelve JSON limpio ES, sin signup. Hit caché 2s coste 0, miss 30-40s coste ~$0.015, precio $0.08/$0.08/$0.05, free-miss si 0 resultados. 10 buyers recurrentes (retención 71-96% en ese tramo) antes que 1000 curiosos.

## Approach
Contrato fijo por delante, router curado por detrás (elegido): una sola ruta por necesidad, actor top por defecto (clockworks~tiktok-scraper 322k users/136M runs validan el camino) + fallback, input schema fijo {searchQuery, maxResults, proxyCountry: ES}, polling interno + Dataset → normaliza → Redis 1h. Si TikTok cambia firma, cambio actorId en .env sin romper API. Doble backend Apify + Scrapfly ASP si Apify cae. Recomendado porque aísla al agente de los 2661 actors y convierte fricción en 1 paso.

## Scope
- **In**: 3 rutas, paywall Base mainnet CDP, router Apify + fallback, normalización {videos:[{id,desc,autor,likes,fecha,hashtags,cover}]}, caché 1h, free-miss, discovery Bazaar con ejemplo output, 3 tools MCP, solo público.
- **Out**: login, contenido privado, bypass paywall, OnlyFans/adulto, dashboard web, multi-sitio (Maps/IG fuera de este spec).

## Boundary Candidates
- `tiktok-contract`: schema fijo + ejemplos + precios + free-miss (lo que ve el agente).
- `tiktok-router`: actorIds, polling, Dataset, normalización, fallback Apify→Scrapfly (lo que no ve).
- `tiktok-paywall`: 402 Base/CDP + verify/settle + ledger (reuso AGENTE COMPARADOR).
- `tiktok-discovery`: Bazaar listing + MCP tools + caché observabilidad.

## Out of Boundary
- No posee cuentas Apify del cliente, ni wallets de compradores, ni infra proxy propia.
- No hace tracking de precios crypto ni veredictos (quedan en AGENTE COMPARADOR).
- No publica datasets ni training.

## Upstream / Downstream
- **Upstream**: AGENTE COMPARADOR `server.py` (paywall/CDP/A2A/MCP a reusar), Apify Store (actors), Scrapfly ASP (fallback parseo `__UNIVERSAL_DATA_FOR_REHYDRATION__`), Redis, CDP facilitator, Bazaar.
- **Downstream**: agentes trend-tracking/UGC/casting que consumen JSON, spec futuro `maps-bridge` que reusará este molde.

## Existing Spec Touchpoints
- **Extends**: ninguno (greenfield, sin specs previas).
- **Adjacent**: AGENTE COMPARADOR (patrón paywall + `/track` a imitar para éxitos/fallos, no overlapping de dominio).

## Constraints
- Solo TikTok público. Si piden login → free-miss + fuera.
- Precios fijos $0.08/$0.08/$0.05; no bajar a $0.001 (commodity) ni subir a $0.50 sin profundidad extra.
- Stack: Python FastAPI (como AGENTE COMPARADOR), puerto 41243, env (.env, APIFY_TOKEN gitignorado), deploy primero local + Caddy existente, VPS después del primer settle real.
- Pago solo Base mainnet USDC vía CDP; testnets fuera del contrato público.

## Validación formal (sequential-thinking 6/6, 2026-10-11)
Plan válido con 8 añadidos críticos antes de spec-init:
1. Versionado `/v1` + `openapi.json` + `llms.txt` + `skill.md` desde día 1 (discovery sin ejemplo no convierte).
2. Rate-limit por wallet compradora + idempotency key (anti-abuso y anti-doble-cobro).
3. Timeout duro 60s + enqueue no-bloqueante: si miss largo, 202 + retry hint, nunca colgar el HTTP.
4. Switch automático de actor + healthcheck (si clockworks muere, fallback sin deploy).
5. Log de coste por llamada (Apify compute + proxy) para no vender a pérdida; alerta si margen <3x.
6. Wallets separadas por proyecto (no reusar payTo de Veredicto) + settle real previo a anunciar cobro.
7. `terms` + `robots/sitemap` + regla solo-público; metadata + cover URL, nunca re-host de video (mitiga ToS TikTok gris).
8. Métrica éxito = 10 buyers con 10+ pagos/mes (tramo 71-96% retención); alerta si retención <70%. Vanity runs fuera.
