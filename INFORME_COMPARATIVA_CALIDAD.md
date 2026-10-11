# Informe comparativo de calidad — TikTok Bridge

**Fecha:** 11 de octubre de 2026  
**Prueba:** exploratoria, en vivo, región España (ES)  
**Proveedores comparados:**
- TikTok Bridge: router del proyecto, actor clockworks~tiktok-scraper.
- API Dojo: actor apidojo/tiktok-scraper ejecutado por Apify.

## Resumen ejecutivo

En estas tres búsquedas, TikTok Bridge fue más consistente y tuvo una latencia bastante estable (6,5–7,3 s). API Dojo devolvió una mayor completitud de campos cuando tuvo éxito, pero su latencia osciló entre 4,8 y 49,2 s y una de las tres búsquedas terminó en timeout a los 50,5 s.

No hay base para declarar un ganador universal en calidad semántica. La muestra es pequeña y se midieron metadatos y textos de tres consultas; no se reprodujeron ni evaluaron los vídeos completos. Lo que sí se ha demostrado es una pérdida de datos corregible en el normalizador de TikTok Bridge.

## Diseño de la prueba

- Consultas idénticas: receta paella, cafeteria madrid y rutina skincare.
- Región declarada: España (ES).
- Máximo solicitado: 10 resultados por consulta.
- Clockworks: searchQueries, resultsPerPage=10, proxyCountryCode=ES.
- API Dojo: keywords, maxItems=10, location=ES, sortType=RELEVANCE, dateRange=DEFAULT.
- No se hicieron pagos x402. Sí se ejecutaron los actores de Apify con el token de API ya configurado en el proyecto. El coste facturado final no se consultó y puede depender de la configuración de la cuenta.

La primera búsqueda se recuperó del conjunto de datos generado en esa ejecución para evitar repetir una llamada que ya había terminado.

## Resultados cuantitativos

| Consulta | Bridge: resultados / latencia | API Dojo: resultados / latencia | Observación |
|---|---:|---:|---|
| receta paella | 10 / 6,5 s | 10 / 49,2 s | Ambos encontraron contenido relevante sobre paella |
| cafeteria madrid | 10 / 7,2 s | 10 / 4,8 s | Ambos encontraron vídeos de cafeterías en Madrid; se repiten algunos IDs |
| rutina skincare | 10 / 7,3 s | 0 / 50,5 s | API Dojo terminó en timeout; no se evalúa relevancia para esta consulta |

### Fiabilidad y latencia

- **Bridge:** 3/3 consultas completadas; latencia media aproximada de 7,0 s.
- **API Dojo:** 2/3 consultas completadas; latencia media de las dos ejecuciones exitosas de 27,0 s. Incluyendo la ejecución fallida, el tiempo medio por intento fue de 34,9 s.
- Cada proveedor devolvió 10 IDs distintos en cada consulta completada; no se observaron IDs duplicados dentro de esas respuestas.

El timeout de API Dojo es un resultado observado en esta muestra, no una estimación de su tasa global de fallos.

## Completitud de los campos

Se midieron siete campos normalizados: id, desc, autor, likes, fecha, hashtags y cover.

| Campo | Bridge (media en 3 consultas) | API Dojo (media en 2 exitosas) |
|---|---:|---:|
| id | 100 % | 100 % |
| desc | 100 % | 100 % |
| autor | 100 % | 100 % |
| likes | 100 % | 100 % |
| fecha | 100 % | 100 % |
| hashtags | 90 % | 85 % |
| cover | **0 %** | 100 % |
| **Completitud total** | **84,3 %** | **97,9 %** |

Este indicador mide la presencia de los siete campos, no su exactitud ni la calidad del contenido. API Dojo se calcula solo sobre las dos búsquedas completadas.

### Hallazgo corregible en TikTok Bridge

El actor Clockworks sí devuelve videoMeta.coverUrl y webVideoUrl en los elementos originales. El normalizador de src/tiktok_router.py usa it.get("video") para buscar video.cover y, como alternativa, covers[0]. En los datos analizados, video y covers no estaban presentes, por lo que cover quedó vacío en los 30 resultados.

**Corrección recomendada:** extraer la portada mediante videoMeta.coverUrl o videoMeta.originalCoverUrl como fallback, y exponer una propiedad url desde webVideoUrl en el contrato JSON. Añadir pruebas unitarias con un fixture realista del esquema Clockworks para evitar regresiones.

## Relevancia: indicio, no verdad de referencia

Se calculó una coincidencia lexical sencilla: proporción de tokens de la consulta encontrados como texto en la descripción o hashtags. Este indicador no comprende sinónimos, intención, contexto del vídeo ni todas las variantes con tilde, por lo que no debe tratarse como una puntuación semántica definitiva.

| Consulta | Bridge: coincidencia lexical media | API Dojo: coincidencia lexical media |
|---|---:|---:|
| receta paella | 95 % | 70 % |
| cafeteria madrid | 75 % | 85 % |
| rutina skincare | 80 % | No evaluable: timeout |
| **Media comparable** | **83,3 %** | **77,5 %** |

Para la primera consulta, API Dojo devuelve varias publicaciones claramente centradas en paella que no contienen necesariamente el token «receta». Esto ilustra la limitación de la métrica: coincidencia lexical baja no equivale siempre a irrelevancia.

La inspección manual de las primeras cuatro muestras de cada ejecución completada mostró contenido de paella relevante en ambos proveedores; para cafeterías, Bridge devolvió cuatro muestras estrechamente relacionadas, mientras que una de las cuatro muestras visibles de API Dojo parecía menos relacionada. Esta revisión es orientativa y se basa solo en las descripciones y hashtags mostrados, no en reproducir el vídeo.

## Solapamiento de datos

Se encontraron vídeos con el mismo ID en los resultados mostrados de ambos proveedores:

- receta paella: 7494665719724952838 y 7520601978334924054.
- cafeteria madrid: 7693276377193155862 y 7688769555790892321.

Esto demuestra que parte del contenido es compartido; no se ha identificado un corpus exclusivo de TikTok Bridge. No demuestra que todos los resultados sean idénticos ni descarta que consultas más amplias puedan revelar diferencias.

## Conclusiones

1. **Fiabilidad/latencia:** Bridge gana en esta muestra: 3/3 resultados con latencia estable de alrededor de 7 s. API Dojo fue irregular y sufrió un timeout.
2. **Completitud:** API Dojo obtiene mejor puntuación en los resultados exitosos, principalmente porque Bridge pierde la portada por un error de mapeo.
3. **Relevancia:** el indicio lexical favorece ligeramente a Bridge en las dos consultas comparables, pero la métrica es débil y los resultados fueron relevantes en ambos sistemas. Se necesita una evaluación humana sobre un conjunto etiquetado más grande.
4. **Exclusividad:** hay solapamiento de IDs entre ambos proveedores; no se demuestra una ventaja de datos exclusivos.
5. **Recomendación:** corregir el normalizador antes de anunciar calidad superior y repetir el benchmark con al menos 30 consultas por categoría, tres repeticiones por consulta y un conjunto manualmente etiquetado. Medir precisión@10, duplicados, campos válidos, antigüedad, tasa de timeout y coste facturado por 1.000 resultados útiles.

## Fuentes públicas de referencia

- Clockworks TikTok Scraper en Apify: https://apify.com/clockworks/tiktok-scraper
- API Dojo TikTok Scraper en Apify: https://apify.com/apidojo/tiktok-scraper

Los precios y valoraciones que se muestran en esas páginas son declaraciones comerciales de los proveedores; esta prueba no verificó la factura real de la cuenta Apify.


---

## Validación posterior a las mejoras — 11 de octubre de 2026

Se corrigió el normalizador y se ejecutó un segundo smoke test en vivo contra la ruta de búsqueda, con las mismas tres consultas de la prueba inicial. Se pidieron 10 resultados por consulta; las llamadas se hicieron directamente a los actores mediante Apify, sin firmar ni liquidar pagos x402.

| Consulta | Resultados | Latencia | IDs únicos | Portada presente | URL pública | Hashtags como strings | Fecha ISO-8601 |
|---|---:|---:|---:|---:|---:|---:|---:|
| receta paella | 10 | 7,80 s | 10/10 | 100 % | 100 % | 100 % | 100 % |
| cafeteria madrid | 10 | 8,42 s | 10/10 | 100 % | 100 % | 100 % | 100 % |
| rutina skincare | 10 | 6,81 s | 10/10 | 100 % | 100 % | 100 % | 100 % |

La relevancia media lexical estimada por la versión posterior fue 0,85, 0,95 y 0,75, respectivamente. Es una heurística útil para ordenar y decidir cuándo consultar una fuente secundaria; no equivale a una evaluación semántica etiquetada. No se deben comparar estos promedios con los del primer script como si fueran una prueba estadística pareada: la normalización de hashtags cambió, el contenido de TikTok cambia con el tiempo y la definición exacta de la métrica inicial no era idéntica.

### Cambios implementados

- El normalizador ahora recupera videoMeta.coverUrl, videoMeta.originalCoverUrl y webVideoUrl; normaliza fechas en ISO-8601 UTC, convierte hashtags a strings, elimina IDs duplicados y conserva métricas de engagement disponibles.
- El ranking de búsqueda añade relevancia y search_meta, con número de fuentes consultadas, uso de fallback, número de resultados, promedio lexical y cobertura de portada/URL. No devuelve identificadores internos de los actores.
- La búsqueda usa un presupuesto global de tiempo, activa fuentes secundarias ante respuestas vacías, escasas, incompletas o de baja relevancia, combina registros por ID y devuelve 202 si todos los proveedores fallan. El fallback no se activa cuando la respuesta primaria ya parece suficientemente completa y relevante.
- Perfil y comentarios tienen fallback configurable. Sus payloads son específicos de cada actor; la normalización de comentarios acepta el usuario anidado de API Dojo y devuelve campos adicionales de ID, identidad pública, fecha, respuestas e idioma cuando están disponibles.
- Las respuestas sin datos útiles usan una caché de cinco minutos; las respuestas con datos usan una hora. Redis sigue siendo prioritario, SQLite es el fallback persistente compartido por REST/MCP y la memoria es el último recurso. El endpoint /health puede indicar qué backend está activo sin revelar tokens ni nombres de actores.
- Los costes de proveedores y de ejecuciones fallidas que no se han verificado se guardan como desconocidos, no como cero.

### Pruebas de regresión

La suite final contiene **43 pruebas automatizadas** que cubren contrato, normalización de ambos esquemas, respaldo/merge/deduplicación, presupuesto de búsqueda, payloads de perfil/comentarios, compatibilidad MCP, caché SQLite compartida entre funciones async y sync, y saneamiento de /health. También se comprobó el protocolo MCP Streamable HTTP en una instancia de prueba: tools/list devuelve cinco herramientas, conservando tres nombres originales y añadiendo aliases de perfil/comentarios.

### Qué queda demostrado y qué no

Queda demostrado que la respuesta normalizada contiene las portadas, URLs, etiquetas y fechas en las tres consultas de prueba, y que el código tiene tests para activar fallbacks y combinar resultados incompletos. El smoke test no demuestra por sí solo que la relevancia sea superior en el mercado. Para sostener esa afirmación hace falta un benchmark mayor, con muchas consultas repetidas y una evaluación humana de relevancia. No se ejecutaron pagos reales x402 en esta validación; las llamadas directas a Apify sí pueden generar costes de proveedor.


### Verificación final del servicio reiniciado

Después de aplicar los cambios, se reiniciaron los servicios locales habituales (REST en 41243 y MCP Streamable HTTP en 41245) y se volvieron a comprobar:

- REST /health: HTTP 200; la caché reporta SQLite compartido entre procesos, y hay proveedores alternativos configurados para búsqueda, perfil y comentarios.
- /openapi.json: HTTP 200 y las tres rutas de TikTok aparecen en el esquema.
- Petición sin firma a /v1/tiktok/search: HTTP 402; el reto tiene los requisitos de pago y el ejemplo ya contiene search_meta y los campos normalizados completos, incluidos cover y url.
- MCP Streamable HTTP: initialize y tools/list responden HTTP 200; aparecen cinco tools (tres nombres originales y dos aliases).
- También se comprobó el endpoint público: la ruta de búsqueda devuelve HTTP 402 sin una firma de pago, con el ejemplo ampliado; los documentos públicos tiktok/skill.md y tiktok/llms.txt responden HTTP 200 y contienen la documentación actualizada.

La verificación fue sin firma ni liquidación x402. El directorio de la caché local SQLite es compartido entre procesos del mismo equipo; para producción distribuida en varias máquinas seguiría siendo preferible Redis o una base compartida con las mismas propiedades.


Se ejecutaron también llamadas MCP reales a las tres herramientas públicas, sin realizar solicitudes HTTP pagadas: tiktok_search devolvió endpoint /v1/tiktok/search, precio 0.08 USDC y el cuerpo q/max; tiktok_profile devolvió /v1/tiktok/perfil y user; tiktok_comments devolvió /v1/tiktok/comments y id/max con precio 0.05 USDC. Las tres respuestas fueron HTTP 200 de MCP y payment_required=true.


---

## Benchmark ampliado en vivo — 11 de octubre de 2026

Se ejecutó un benchmark adicional con seis consultas y tres fuentes: Clockworks principal, Clockworks fallback y API Dojo. Se solicitaron hasta ocho vídeos por fuente y consulta, región ES y timeout de 18 segundos por actor. Las 18 llamadas directas produjeron los datos base; luego se reprodujeron esas respuestas en el router para medir su política sin repetir las mismas llamadas. No se hicieron pagos x402; las ejecuciones directas de Apify pueden generar costes y la factura real no se consultó.

### Resumen

| Sistema | Peticiones respondidas | Consultas con resultados | Errores/timeouts | Latencia media directa o estimada | Completitud del esquema con resultados | Portada y URL con resultados |
|---|---:|---:|---:|---:|---:|---:|
| Clockworks principal | 5/6 (83,3 %) | 5/6 (83,3 %) | 1 | 9,64 s | 98,13 % | 100 % / 100 % |
| Clockworks fallback | 6/6 (100 %) | 6/6 (100 %) | 0 | 8,45 s | 98,44 % | 100 % / 100 % |
| API Dojo | 5/6 (83,3 %) | 2/6 (33,3 %) | 1 | 8,06 s | 98,44 % | 100 % / 100 % |
| TikTok Bridge (router) | 6/6 (100 %) | 6/6 (100 %) | 0 en la reproducción | ~11,32 s de upstream modelado | 98,44 % | 100 % / 100 % |

Una respuesta vacía de API Dojo cuenta como una petición completada, pero no como una consulta con resultados. En esta muestra, API Dojo respondió sin resultados en tres consultas y agotó el timeout en una; las otras dos devolvieron ocho resultados. Clockworks principal agotó el timeout en una consulta. El fallback de Clockworks devolvió ocho resultados en las seis consultas.

### Resultado por consulta

- receta paella: los tres proveedores devolvieron ocho resultados; Bridge usó el primario.
- cafeteria madrid: los tres proveedores devolvieron ocho resultados; Bridge usó el primario.
- rutina skincare: Clockworks y su fallback devolvieron ocho; API Dojo respondió vacío. Bridge usó el primario.
- entrenamiento en casa principiantes: Clockworks y su fallback devolvieron ocho; API Dojo respondió vacío. Bridge usó el primario.
- consejos para entrevistas de trabajo: los dos actores Clockworks devolvieron ocho; API Dojo agotó el timeout. Bridge usó el primario.
- viaje barato japon: Clockworks principal agotó el timeout; el fallback devolvió ocho; API Dojo respondió vacío. Bridge cambió al fallback y devolvió ocho.

### Interpretación y límites

El fallback de Clockworks tuvo la mejor disponibilidad observada en esta muestra. Bridge entregó resultados en las seis consultas y activó el fallback en una, precisamente cuando el primario agotó el timeout. La completitud condicional de 98,44 % y la cobertura de portada/URL de 100 % se calculan solo entre respuestas con resultados; se mantienen también promedios que cuentan fallos y vacíos como cero para que no queden ocultos.

La relevancia lexical media fue 0,600 para Clockworks principal, 0,555 para el fallback, 0,687 para API Dojo (solo dos consultas con resultados) y 0,555 para Bridge. Estos valores no son comparables como una clasificación definitiva porque la métrica es solo una coincidencia de términos y las fuentes no devolvieron resultados para la misma cantidad de consultas. Es necesario usar la plantilla de revisión manual para medir Precision@5 antes de afirmar que un sistema entrega resultados semánticamente mejores.

### Archivos del benchmark

- BENCHMARK_TIKTOK_2026-10-11.md: informe y resultados por consulta.
- BENCHMARK_TIKTOK_2026-10-11.csv: métricas por fuente y consulta.
- BENCHMARK_TIKTOK_2026-10-11.json: datos completos y métricas agregadas.
- BENCHMARK_TIKTOK_REVISION_MANUAL.csv: primeras cinco posiciones para etiquetar relevancia de 0 (no relevante) a 2 (relevante).
- benchmark_tiktok_bridge.py: runner reproducible; ejecutarlo vuelve a llamar a Apify y puede generar costes.
- finalize_benchmark_tiktok.py: recalcula el informe sin repetir las consultas y separa respuestas vacías de errores de transporte.
