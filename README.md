# TIKTOK BRIDGE — puente x402, 1 call sustituye 6 de Apify
Contrato fijo por delante, router curado por detrás.

## Rutas (solo 3)
- POST /tiktok/search {q, max} $0.08
- POST /tiktok/perfil {user} $0.08
- POST /tiktok/comments {id, max} $0.05
- Regla: free-miss si 0 resultados. Sin resultado no se cobra.

## Paso 1 (hoy): mock + contrato
server_min.py expone las 3 rutas con datos cacheados reales, sin Apify, sin cobro.
Objetivo: validar contrato + schema + ejemplos en el 402.

## Paso 2: paywall x402 Base (reusar server.py de AGENTE COMPARADOR)
Copiar _methods(), x402_challenge(), facilitador CDP. Precios 80000 / 80000 / 50000.

## Paso 3: router Apify por detrás
tiktok_router.py: actorId clockworks~tiktok-scraper, input {searchQuery, maxResults, proxyCountry: ES},
polling 30s, Dataset → normaliza → caché 1h. Nunca exponer actorId al agente.

## Paso 4: discovery Bazaar + MCP
description + ejemplo output en el 402. 3 tools MCP.
