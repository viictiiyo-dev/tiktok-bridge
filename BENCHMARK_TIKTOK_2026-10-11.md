# Benchmark TikTok Bridge — resultados en vivo

- Fecha UTC: 2026-10-11T13:02:08+00:00
- Consultas: 6; máximo 8 resultados por proveedor y consulta.
- Región: ES; timeout por actor: 18 s.
- No se hicieron pagos x402. Sí se ejecutaron llamadas directas a Apify y pueden haberse generado costes; no se consultó la factura.
- Bridge se evaluó reproduciendo las respuestas reales obtenidas en esta misma ronda, sin volver a pagar las mismas fuentes para comparar su política de normalización y fallback.
- Una respuesta vacía es una petición completada sin resultados; un error/timeout sí es un fallo.
- La relevancia lexical es una proxy basada en tokens de descripción/hashtags, no un juicio humano ni una medida semántica definitiva.

## Resumen por sistema

| Sistema | Respuesta HTTP útil/completada | Consultas con resultados | Errores | Resultados medios por consulta | Latencia medida / estimada | Completitud con resultados | Portada con resultados | URL con resultados | Relevancia lexical media con resultados |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Clockworks principal | 5/6 (83.3%) | 5/6 (83.3%) | 1 | 6.67 | 9.638 s directa | 98.13% | 100.0% | 100.0% | 0.6 |
| Clockworks fallback | 6/6 (100.0%) | 6/6 (100.0%) | 0 | 8.0 | 8.453 s directa | 98.44% | 100.0% | 100.0% | 0.555 |
| API Dojo | 5/6 (83.3%) | 2/6 (33.3%) | 1 | 2.67 | 8.055 s directa | 98.44% | 100.0% | 100.0% | 0.687 |
| TikTok Bridge (router) | 6/6 (100.0%) | 6/6 (100.0%) | 0 | 8.0 | ~11.32 s upstream modelados | 98.44% | 100.0% | 100.0% | 0.555 |

### Agregados adicionales

| Sistema | Completitud media contando fallos/vacíos como 0 | Portada en todos los intentos | URL en todos los intentos | Media de relevancia con vacíos/fallos como 0 |
|---|---:|---:|---:|---:|
| Clockworks principal | 81.77% | 83.33% | 83.33% | 0.5 |
| Clockworks fallback | 98.44% | 100.0% | 100.0% | 0.555 |
| API Dojo | 32.81% | 33.33% | 33.33% | 0.229 |
| TikTok Bridge (router) | 98.44% | 100.0% | 100.0% | 0.555 |

## Resultados por consulta

| Consulta | Sistema | Estado | n | Latencia/overhead | Esquema | Portada | URL | Relevancia lexical | Fuentes que usó Bridge |
|---|---|---|---:|---:|---:|---:|---:|---:|---|
| receta paella | Clockworks principal | ok | 8 | 8.39 s | 96.88% | 100.0% | 100.0% | 0.812 | — |
| receta paella | Clockworks fallback | ok | 8 | 8.031 s | 96.88% | 100.0% | 100.0% | 0.812 | — |
| receta paella | API Dojo | ok | 8 | 8.282 s | 98.44% | 100.0% | 100.0% | 0.562 | — |
| receta paella | TikTok Bridge (router) | ok | 8 | ~8.39 s upstream modelados; 0.109 s de overhead local | 96.88% | 100.0% | 100.0% | 0.812 | Clockworks principal |
| cafeteria madrid | Clockworks principal | ok | 8 | 8.735 s | 100.0% | 100.0% | 100.0% | 0.688 | — |
| cafeteria madrid | Clockworks fallback | ok | 8 | 6.828 s | 100.0% | 100.0% | 100.0% | 0.625 | — |
| cafeteria madrid | API Dojo | ok | 8 | 8.656 s | 98.44% | 100.0% | 100.0% | 0.812 | — |
| cafeteria madrid | TikTok Bridge (router) | ok | 8 | ~8.735 s upstream modelados; 0.0 s de overhead local | 100.0% | 100.0% | 100.0% | 0.688 | Clockworks principal |
| rutina skincare | Clockworks principal | ok | 8 | 8.078 s | 98.44% | 100.0% | 100.0% | 0.75 | — |
| rutina skincare | Clockworks fallback | ok | 8 | 7.328 s | 98.44% | 100.0% | 100.0% | 0.812 | — |
| rutina skincare | API Dojo | empty | 0 | 2.844 s | 0.0% | 0.0% | 0.0% | 0.0 | — |
| rutina skincare | TikTok Bridge (router) | ok | 8 | ~8.078 s upstream modelados; 0.0 s de overhead local | 98.44% | 100.0% | 100.0% | 0.75 | Clockworks principal |
| entrenamiento en casa principiantes | Clockworks principal | ok | 8 | 7.265 s | 98.44% | 100.0% | 100.0% | 0.292 | — |
| entrenamiento en casa principiantes | Clockworks fallback | ok | 8 | 10.0 s | 98.44% | 100.0% | 100.0% | 0.292 | — |
| entrenamiento en casa principiantes | API Dojo | empty | 0 | 6.141 s | 0.0% | 0.0% | 0.0% | 0.0 | — |
| entrenamiento en casa principiantes | TikTok Bridge (router) | ok | 8 | ~7.265 s upstream modelados; 0.0 s de overhead local | 98.44% | 100.0% | 100.0% | 0.292 | Clockworks principal |
| consejos para entrevistas de trabajo | Clockworks principal | ok | 8 | 6.781 s | 96.88% | 100.0% | 100.0% | 0.458 | — |
| consejos para entrevistas de trabajo | Clockworks fallback | ok | 8 | 8.437 s | 96.88% | 100.0% | 100.0% | 0.458 | — |
| consejos para entrevistas de trabajo | API Dojo | error | 0 | 18.485 s | 0.0% | 0.0% | 0.0% | 0.0 | — |
| consejos para entrevistas de trabajo | TikTok Bridge (router) | ok | 8 | ~6.781 s upstream modelados; 0.0 s de overhead local | 96.88% | 100.0% | 100.0% | 0.458 | Clockworks principal |
| viaje barato japon | Clockworks principal | error | 0 | 18.578 s | 0.0% | 0.0% | 0.0% | 0.0 | — |
| viaje barato japon | Clockworks fallback | ok | 8 | 10.093 s | 100.0% | 100.0% | 100.0% | 0.333 | — |
| viaje barato japon | API Dojo | empty | 0 | 3.922 s | 0.0% | 0.0% | 0.0% | 0.0 | — |
| viaje barato japon | TikTok Bridge (router) | ok | 8 | ~28.671 s upstream modelados; 0.0 s de overhead local | 100.0% | 100.0% | 100.0% | 0.333 | Clockworks principal > Clockworks fallback |

## Lectura del resultado

- Clockworks principal: 5/6 consultas con resultados; una petición agotó el timeout. En las consultas que sí devolvieron datos, la completitud media del esquema es 98.13%.
- Clockworks fallback: 6/6 consultas con resultados; completitud media condicional 98.44%. Su media de latencia directa incluye todos los intentos.
- API Dojo: 5/6 peticiones respondieron (incluidas las vacías), 2/6 devolvieron resultados y 1 terminó en error/timeout. La baja tasa de respuestas con datos es un hallazgo de esta muestra, no una tasa universal.
- Bridge: 6/6 consultas con resultados; usó fallback en 1/6. La latencia upstream modelada es la suma de las duraciones medidas de las fuentes que el router habría consultado; no es una petición end-to-end real al endpoint HTTP.
- La completitud condicional evalúa ocho campos: id, desc, autor, likes, fecha, hashtags, cover y url. Los promedios de todos los intentos se muestran aparte para no esconder fallos/vacíos.
- La coincidencia lexical puede infravalorar sinónimos y sobrevalorar palabras coincidentes sin relación semántica. No declarar una victoria semántica sin evaluación humana.

## Revisión manual

En BENCHMARK_TIKTOK_REVISION_MANUAL.csv hay hasta cinco primeros resultados por sistema y consulta. Completa human_relevance_0_2 con 0=no relevante, 1=parcial y 2=relevante, y añade notas breves. Así se obtiene una medida real de Precision@5 y se puede comparar el ranking con la misma pauta para todos.

## Archivos generados

- BENCHMARK_TIKTOK_2026-10-11.json: resultados completos, respuestas y métricas.
- BENCHMARK_TIKTOK_2026-10-11.csv: métricas por consulta/sistema.
- BENCHMARK_TIKTOK_REVISION_MANUAL.csv: muestra para etiquetado humano.
- benchmark_tiktok_bridge.py: runner reproducible; vuelve a consultar Apify y puede generar costes.
