# Benchmark de comentarios TikTok

- Fecha UTC: 2026-10-11 (prueba en vivo)
- Muestra: 3 v?deos p?blicos, 2 actores, m?ximo 20 comentarios por v?deo/actor; 6 ejecuciones.
- No se realizaron pagos x402. Las llamadas directas a Apify s? generaron uso facturable.
- Uso observado en metadatos de ejecuci?n de Apify: **$0.084** para estas seis llamadas ($0.075 Clockworks + $0.009 API Dojo). La factura final no se consult?.
- Hubo tres ejecuciones diagn?sticas adicionales: una expir? con $0.0009 de uso y dos variantes inv?lidas fallaron sin uso; no est?n incluidas en el total del benchmark.
- No se guardan textos de comentarios, IDs de comentarios ni nombres de usuarios; solo m?tricas agregadas.

| V?deo | Proveedor | ?tiles | ?nicos | Duplicados | Autor % | ID % | Fecha % | Likes % | Latencia s | Estado | Uso Apify USD |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|
| paella | Clockworks principal | 20 | 20 | 0 | 100.0 | 100.0 | 100.0 | 100.0 | 9.672 | SUCCEEDED | $0.0250 |
| paella | API Dojo fallback | 0 | 0 | 0 | 0.0 | 0.0 | 0.0 | 0.0 | 25.469 | TIMED-OUT | $0.0030 |
| cafeteria | Clockworks principal | 20 | 20 | 0 | 100.0 | 100.0 | 100.0 | 100.0 | 17.968 | SUCCEEDED | $0.0250 |
| cafeteria | API Dojo fallback | 0 | 0 | 0 | 0.0 | 0.0 | 0.0 | 0.0 | 25.484 | TIMED-OUT | $0.0030 |
| skincare | Clockworks principal | 20 | 20 | 0 | 100.0 | 100.0 | 100.0 | 100.0 | 11.485 | SUCCEEDED | $0.0250 |
| skincare | API Dojo fallback | 0 | 0 | 0 | 0.0 | 0.0 | 0.0 | 0.0 | 25.5 | TIMED-OUT | $0.0030 |

## Hallazgos

1. **Clockworks:** 3/3 ejecuciones completadas, 20 comentarios utilizables por v?deo y cero duplicados observados en la muestra. Latencia media: 13,0 s.
2. **API Dojo:** 0/3 ejecuciones utilizables; las tres terminaron en timeout bajo la cuenta/configuraci?n de Apify utilizada. El actor no debe contarse como fallback operativo hasta resolver el plan/timeout y repetir la prueba.
3. **Coste real observado:** Clockworks registr? $0.025 de uso por ejecuci?n de 20 comentarios ($0.075 total). Aunque la tarifa p?blica anuncia un precio desde $0.50/1.000 comentarios, el coste efectivo observado aqu? fue $1.25/1.000 por el uso total reportado por Apify. El valor puede incluir componentes de uso/ejecuci?n y no sustituye la factura.
4. Con el precio actual de $0.05 por llamada de comentarios, 20 comentarios dejaron una contribuci?n bruta indicativa de $0.025 (50%) antes de liquidaci?n x402, infraestructura, soporte y otros costes. **No extrapolar a 50 comentarios**: ese l?mite no se prob? en vivo.
5. El contador p?blico de comentarios del v?deo no es una verdad de referencia: puede incluir respuestas, comentarios eliminados/filtrados o elementos inaccesibles. Esta prueba compara el l?mite solicitado, no la exhaustividad de todos los comentarios.

## Siguiente acci?n recomendada

- Mantener Clockworks como principal para comentarios por ahora.
- No cambiar autom?ticamente el fallback de producci?n bas?ndose solo en esta prueba: primero resolver la limitaci?n de plan/timeout de API Dojo o probar un tercer actor con coste acotado.
- Medir una ejecuci?n de 50 comentarios antes de confirmar que el precio de 0.05 USDC deja margen suficiente.
- Para una prueba de calidad completa, revisar manualmente una muestra de comentarios sin persistir datos personales innecesarios.
