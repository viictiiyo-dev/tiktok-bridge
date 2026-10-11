# TikTok Bridge — acceso a datos públicos de TikTok para agentes

API REST de pago por consulta con x402 en Base mainnet. Mantiene un contrato JSON normalizado y abstrae la selección de scraper, los reintentos, la deduplicación, el ranking y la caché.

## Endpoints

- POST /v1/tiktok/search con {"q":"paella","max":20} — 0.08 USDC, entre 1 y 20 resultados por consulta al precio actual.
- POST /v1/tiktok/perfil con {"user":"cocina_es"} — 0.08 USDC.
- POST /v1/tiktok/comments con {"id":"7635981647359380758","max":50} — 0.05 USDC. Cada comentario incluye id, autor, handle/nombre públicos, texto, likes si están disponibles, fecha ISO-8601, respuestas e idioma cuando el proveedor los devuelve.

Solo consulta contenido público. No requiere cuenta de TikTok, no accede a perfiles privados y no vuelve a alojar vídeos.

## Calidad y fiabilidad de búsqueda

La búsqueda usa Clockworks como proveedor primario y consulta fuentes secundarias cuando la respuesta es vacía, escasa, le faltan metadatos esenciales o no coincide mínimamente con los términos de la consulta. Fusiona los resultados y deduplica por ID. Perfil y comentarios también tienen proveedor de respaldo cuando el primario falla o devuelve una respuesta vacía; el perfil secundario se usa además si faltan metadatos del creador. Los proveedores secundarios solo se invocan cuando la calidad observada lo justifica. La puntuación relevancia va de 0 a 1; no es una evaluación semántica perfecta.

Las búsquedas tienen un presupuesto global limitado. Si los proveedores fallan, la API devuelve 202 con una indicación de reintento; no presenta un error de backend como si la búsqueda no tuviera resultados. Si los proveedores responden correctamente pero no hay vídeos utilizables, devuelve free_miss y no liquida el pago.

## Esquema de vídeo

Cada vídeo incluye los campos estables id, desc, autor, likes, fecha, hashtags, cover y url. fecha se normaliza a ISO-8601 UTC y hashtags es una lista de strings. Los campos adicionales pueden incluir views, comments, shares, saves, duration, language, is_ad, autor_nombre, autor_usuario y relevancia. duration mantiene segundos fraccionarios cuando el proveedor los devuelve. Las respuestas de búsqueda incluyen search_meta con fuentes consultadas (solo contador), si se usó respaldo, número de resultados, relevancia media aproximada y cobertura de portada/URL. Un dato que el proveedor no entrega se deja vacío o null, no se inventa.

## Caché

- Los resultados con datos se conservan durante una hora.
- Redis es el backend preferido. Si no está disponible y CACHE_REQUIRE_REDIS=0, SQLite mantiene una caché persistente compartida por REST y MCP; la memoria solo se usa si fallan ambos.
- Las respuestas sin resultados usan una caché corta de cinco minutos para que una ausencia transitoria no oculte publicaciones nuevas durante una hora.
- Las claves normalizan espacios y mayúsculas, y unifican ID y URL larga de un mismo vídeo cuando es posible.
- /health informa si la caché es Redis, SQLite o memoria y muestra contadores de fallos del scraper sin publicar nombres internos de actores ni tokens.

## MCP

- Streamable HTTP: https://veredicto.dpdns.org/tiktok-mcp/mcp
- Herramientas recomendadas: tiktok_search, tiktok_profile, tiktok_comments.
- Se conservan tiktok_perfil_info y tiktok_comments_info por compatibilidad.
- En modo público las tools devuelven el endpoint REST, el cuerpo de la consulta y los pasos para un cliente HTTP compatible con x402. No firman pagos por el usuario.
- MCP_ALLOW_FREE_SEARCH=1 habilita ejecución sin cobro para una instancia privada del operador; no debe activarse en un servicio MCP público.

## Cliente x402 de ejemplo

Para una consulta REST desde código Node.js, el proyecto incluye examples/tiktok_bridge_x402_client.mjs, basado en el SDK oficial x402. Requiere Node.js 20+, @x402/fetch, @x402/evm y viem. La muestra tiene un bloqueo deliberado: no hace ninguna llamada hasta que la variable TIKTOK_BRIDGE_ALLOW_LIVE_PAYMENT sea exactamente YES. Una llamada de búsqueda puede pagar 0.08 USDC en Base mainnet. Usa solo una wallet con fondos limitados y revisa el código antes de habilitar pagos.

El MCP público continúa entregando instrucciones para REST, no firma ni ejecuta pagos por el consumidor. El cliente de ejemplo reduce la fricción para aplicaciones que integren x402 a nivel REST; no convierte el MCP vanilla en un cliente pagador automático.

Para un agente MCP pagador, `examples/tiktok_bridge_paid_mcp_client.mjs` muestra el patrón de Coinbase x402 Bazaar (`@x402/mcp`) con consentimiento explícito y límite de búsqueda. Este patrón depende de que el recurso REST de TikTok Bridge esté indexado en Bazaar y de usar el `toolName` que publique `search_resources`; la disponibilidad en el catálogo todavía debe verificarse antes de anunciarlo como una integración de un solo paso.

## Rentabilidad y métricas

- Ejecuta python auditar_rentabilidad.py para regenerar AUDITORIA_RENTABILIDAD_2026-10-11.md con el ledger local y los registros de costes. No llama a proveedores ni realiza pagos.
- Las estimaciones de coste usan tarifas públicas PPR anunciadas por los actores; no sustituyen la factura de la cuenta Apify. Fallos y respuestas vacías quedan como coste desconocido.
- Las nuevas ejecuciones correlacionan el coste del actor con la venta usando request_id, un fingerprint compartido que no es la consulta ni la firma de pago.
- src/metrics_tiktok.jsonl cuenta respuestas HTTP por ruta/estado, con latencia, sin guardar IP, wallet, texto de consulta ni firma. /stats expone agregados de 30 días solo cuando se configura STATS_TOKEN.
- El límite de 20 resultados evita que el precio fijo de 0.08 USDC cubra de forma insuficiente una respuesta de 50 elementos con la tarifa pública de inicio actual. Los precios públicos pueden cambiar y deben revisarse.

## Benchmark de comentarios (11-10-2026)

El benchmark `BENCHMARK_COMENTARIOS_TIKTOK_2026-10-11.md` compara 3 v?deos con hasta 20 comentarios por actor. Clockworks complet? 3/3 llamadas, con 20 comentarios utilizables por v?deo y coste de uso observado de $0.025 por ejecuci?n en metadatos de Apify. API Dojo agot? el tiempo en 3/3 llamadas con la cuenta/plan usado. La factura no se concili? y no se verific? el coste para 50 comentarios. No se ha cambiado el fallback de producci?n por esta muestra.

Runner: `benchmark_comentarios_tiktok.py`. Requiere activar expl?citamente `TIKTOK_COMMENTS_BENCHMARK_LIVE=YES`; realiza llamadas a Apify que pueden generar costes y guarda solo m?tricas agregadas.

## Pruebas

Ejecutar en la raíz del proyecto:

    python -m pytest -q

No afirmes margen neto hasta conciliar estos logs con la factura real de Apify y los gastos de infraestructura.
