# Requirements Document — tiktok-bridge

## Introduction
Puente x402 que expone TikTok público (search, perfil, comments) a agentes IA con 1 fetch + wallet, sin cuenta Apify. Sustituye 6 pasos (cuenta, token, run async, polling, dataset, proxy) por 1 llamada pagada en USDC Base. Reusa paywall CDP de AGENTE COMPARADOR. Solo contenido público, free-miss si 0 resultados.

## Boundary Context (Optional)
- **In scope**: 3 rutas `/v1/tiktok/search|perfil|comments`, paywall Base mainnet, router Apify + fallback, normalización, caché 1h, discovery Bazaar, 3 tools MCP.
- **Out of scope**: login, contenido privado, bypass paywalls, adulto/OnlyFans, dashboard web, Maps/IG (specs futuros).
- **Adjacent expectations**: AGENTE COMPARADOR aporta patrón paywall/ledger/MCP; no se duplica su dominio crypto-veredicto.

## Requirements

### Requirement 1: Contrato fijo versionado
**Objective:** As a agente comprador, I want 3 rutas fijas con schema estable, so that integro una vez y no rompo cuando TikTok cambie.

#### Acceptance Criteria
1. When el agente llama `POST /v1/tiktok/search {q, max}`, the system shall devolver `{videos:[{id,desc,autor,likes,fecha,hashtags,cover}]}` o free-miss `{"videos":[],"free_miss":true}` sin cobrar.
2. When el agente llama `POST /v1/tiktok/perfil {user}`, the system shall devolver `{user,bio,followers,ultimos[]}` o free-miss.
3. When el agente llama `POST /v1/tiktok/comments {id, max}`, the system shall devolver `{id,comments:[{autor,texto,likes}]}` o free-miss.
4. Where el contrato cambie, the system shall versionar `/v2` y mantener `/v1` 90 días.
5. The system shall exponer `openapi.json`, `llms.txt` y `skill.md` desde el día 1.

### Requirement 2: Paywall x402 Base con free-miss
**Objective:** As a operador, I want cobrar $0.08/$0.08/$0.05 solo con resultado, so that la retención supere al precio.

#### Acceptance Criteria
1. When llega POST sin `PAYMENT-SIGNATURE`, the system shall responder 402 con reto v2 + `description` + ejemplo output + `OutputConfig` Bazaar.
2. If hay 0 resultados, then the system shall aplicar free-miss y no llamar a `/settle`.
3. While el pago es válido, the system shall verificar por facilitador CDP y liquidar antes de devolver el recurso.
4. Where el pago falta o es inválido, the system shall devolver 402 con `how` claro, nunca 500.
5. The system shall usar wallet separada de Veredicto y registrar solo liquidaciones `settled_by_facilitator` en el ledger.

### Requirement 3: Router curado con fallback y caché
**Objective:** As a operador, I want un router que oculte los 2661 actors, so that el agente ve 1 contrato y yo cambio backend sin romper nada.

#### Acceptance Criteria
1. When hay miss, the system shall lanzar actor por defecto `clockworks~tiktok-scraper` con `{searchQuery, maxResults, proxyCountry: ES}` y fallback al secundario si falla.
2. When el run tarda >60s o hay captcha duro, the system shall devolver 202 + retry-hint y encolar, nunca colgar el HTTP.
3. While hay Dataset, the system shall normalizar al schema fijo y guardar en caché 1h key `tiktok:q`.
4. Where hay hit de caché, the system shall responder en <2s con coste 0.
5. The system shall registrar coste (compute + proxy) por llamada y alertar si margen <3x.

### Requirement 4: Middleware, límites y observabilidad
**Objective:** As a operador, I want middleware ordenado y límites, so that el puente no se abusa ni se cae.

#### Acceptance Criteria
1. When llega cualquier request salvo `/health`, the system shall aplicar rate-limit por IP y por wallet compradora vía middleware HTTP (`@app.middleware("http")` con `BaseHTTPMiddleware`; gotcha Context7: solo soporta tipo `http`, orden exterior→interior).
2. If se supera el límite, then the system shall devolver 429 con retry en 60s.
3. While hay cobro duplicado, the system shall usar idempotency key para no doble-settle.
4. Where el actor top falla (healthcheck), the system shall cambiar a fallback automáticamente.
5. The system shall exponer `/health`, `/stats` con token y contadores ventas/retos/ventas separando maduros de pendientes.

### Requirement 5: Discovery y límites legales
**Objective:** As a agente descubridor, I want encontrar el puente en Bazaar/MCP con ejemplo real, so that lo uso sin leer docs.

#### Acceptance Criteria
1. When el facilitador lista recursos, the system shall publicar description + ejemplo output + `path_params_schema` por ruta.
2. When un host MCP lista tools, the system shall ofrecer `tiktok-search`, `tiktok-perfil`, `tiktok-comments`.
3. While la query pide login/privado/paywall-bypass, the system shall responder free-miss + fuera.
4. Where el contenido es video, the system shall devolver metadata + cover URL, nunca re-host.
5. The system shall publicar `terms`, `robots.txt` y `sitemap.xml`, y medir éxito como 10 buyers con 10+ pagos/mes con alerta si retención <70%.
