---
name: tiktok-bridge-search
description: Busca vídeos públicos de TikTok y devuelve JSON normalizado, con URL, portada, fecha ISO-8601 y métricas disponibles. Pago por petición vía x402 en Base mainnet.
---

# TikTok Bridge — consultas TikTok para agentes

Puente x402 con un contrato JSON normalizado para agentes. La búsqueda usa respaldo entre proveedores cuando la respuesta es vacía, escasa o lexicalmente poco relevante; fusiona registros duplicados, clasifica resultados por una heurística lexical y aplica caché. Solo contenido público. No accede a perfiles privados ni a vídeos privados.

## Búsqueda — x402 en Base mainnet

- 0.08 USDC por petición, máximo 20 vídeos (max entre 1 y 20): POST https://veredicto.dpdns.org/v1/tiktok/search
- Red: Base mainnet, CAIP-2 eip155:8453, USDC. Sin suscripción. Nunca compartas claves privadas.

Primero envía la solicitud sin firma para obtener HTTP 402:

    POST https://veredicto.dpdns.org/v1/tiktok/search
    Content-Type: application/json

    {"q":"paella","max":20}

Un cliente x402 compatible firma el reto y reintenta con PAYMENT-SIGNATURE y el mismo JSON. Con pago válido devuelve JSON y PAYMENT-RESPONSE. Si los proveedores responden pero no hay vídeos utilizables, devuelve free_miss sin settle. Si los proveedores fallan, devuelve 202 con retry-hint en lugar de confundir el error con ausencia de resultados.

Respuesta de búsqueda: q, videos, search_meta, cached y ts. search_meta informa el número de fuentes consultadas sin revelar sus IDs, si hubo respaldo, número de resultados, relevancia media lexical y cobertura de portada/URL. Cada vídeo contiene id, desc, autor, likes, fecha, hashtags, cover y url; los campos disponibles incluyen autor_nombre, autor_usuario, views, comments, shares, saves, duration, language, is_ad y relevancia. fecha es ISO-8601 UTC; hashtags es una lista de strings; los datos no disponibles quedan como null o cadena vacía. relevancia es una heurística lexical orientativa entre 0 y 1.

## Perfil y comentarios

- POST https://veredicto.dpdns.org/v1/tiktok/perfil con {"user":"cocina_es"} — 0.08 USDC. Devuelve bio, seguidores y publicaciones recientes.
- POST https://veredicto.dpdns.org/v1/tiktok/comments con {"id":"7635981647359380758","max":50} — 0.05 USDC. Devuelve ID, autor, handle/nombre, texto, likes, fecha ISO-8601, respuestas e idioma cuando estén disponibles; campos desconocidos se dejan como null/cadena vacía.
- Un resultado sin datos no se liquida. Los fallos de proveedor se devuelven como reintento.

La respuesta de comentarios a?ade `comments_meta` con cantidades solicitadas/entregadas, duplicados por ID, cobertura de campos, origen l?gico (`primary`/`fallback`) y `exhaustive=false`. Esto mide la respuesta observada y no garantiza que TikTok exponga todos los comentarios.

## MCP

- Streamable HTTP: https://veredicto.dpdns.org/tiktok-mcp/mcp
- Herramientas recomendadas: tiktok_search, tiktok_profile, tiktok_comments.
- Compatibilidad: tiktok_perfil_info y tiktok_comments_info siguen disponibles como alias.
- MCP público devuelve las instrucciones REST x402; no firma pagos. MCP_ALLOW_FREE_SEARCH=1 solo debe habilitarse en una instancia privada del operador. En ese modo las tres herramientas devuelven JSON normalizado y usan las claves canónicas compartidas por REST a través de Redis o del respaldo SQLite. La memoria es el último recurso y no se comparte entre procesos.
