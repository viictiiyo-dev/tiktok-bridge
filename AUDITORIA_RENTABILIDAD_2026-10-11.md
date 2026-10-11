# Auditoría de rentabilidad — TikTok Bridge

**Generada:** 2026-10-11 13:35 UTC. Solo lee ficheros y SQLite locales; no llama a Apify, no consulta carteras ni ejecuta pagos.

## 1. Ingresos realmente registrados

- Liquidaciones registradas con settled_by_facilitator=true: **7**.
- Ingreso bruto del ledger: **0.560000 USDC** (no es beneficio neto).
- Transacciones con hash no vacío y únicos: **7**.
- Direcciones pagadoras distintas: **1**.
- Tipos de operación: {"search": 7}.
- Identificadores anonimizados de pagadores (SHA-256 prefijo; no son direcciones): febea25c.

Interpretación: el registro solo acredita un pagador distinto en la muestra local. No basta para afirmar demanda externa ni retención. No se infiere si esa dirección pertenece al operador o a un cliente.

## 2. ¿Podemos calcular el margen real por venta?

- Ventas anteriores sin request_id común con el ledger de costes: **7/7**.
- Ventas con identificador correlacionable: **0/7**.
- Registros históricos de coste con esquema antiguo/no comparable: **26**.
- Registros de coste sin estimación fiable (fallo, vacío, proveedor sin tarifa verificada): **7** de 33.
- Registros de coste con estimación PPR pública actual: **0**, suma estimada **$0.000000**.
- IDs de peticiones con coste pero sin venta liquidada correlacionada: **0**, coste estimado conocido $0.000000 y **0** intentos de coste desconocido.
- Eventos HTTP instrumentados disponibles: **0**. Contadores actuales: sin histórico; la instrumentación acaba de añadirse.

Conclusión: no se puede reconstruir el coste de cada venta histórica porque los logs previos no compartían identificador y también incluyen pruebas/benchmark. La suma de costes del archivo no debe restarse sin más a los ingresos del ledger. Desde la nueva instrumentación, los costes de proveedor y la venta usan el mismo hash de correlación, sin guardar la consulta ni la firma de pago.

## 3. Economía unitaria de búsqueda (tarifas públicas de referencia)

La página de Clockworks anuncia precio desde $1.70/1.000 resultados para el scraper principal; el actor alternativo aparece desde $1.00/1.000. API Dojo anuncia $0.30/1.000 posts. Son precios públicos de referencia, no la factura verificada de esta cuenta. El cálculo es PPR sobre resultados y no cuantifica coste de fallos/vacíos, gastos ajenos al PPR, servidor ni soporte.

| Escenario | Coste PPR estimado | Ingreso | Margen antes de otros gastos | Margen % |
|---|---:|---:|---:|---:|
| 10 resultados, solo principal | $0.017000 | $0.080000 | $0.063000 | 78.8% |
| 20 resultados, solo principal | $0.034000 | $0.080000 | $0.046000 | 57.5% |
| 50 resultados, solo principal | $0.085000 | $0.080000 | $-0.005000 | -6.3% |
| 20 resultados desde principal + 20 desde fallback | $0.054000 | $0.080000 | $0.026000 | 32.5% |

El límite anterior de 50 resultados podía hacer que el coste de lista del proveedor principal fuera aproximadamente $0.085, por encima del ingreso de $0.08, antes de considerar cualquier fallback. Se ha limitado la búsqueda pública y MCP a 1–20 resultados por consulta al precio actual. A 20 resultados, la comparación de PPR sola deja $0.046 de margen bruto estimado con el actor principal, pero solo $0.026 si ambos actores producen 20 elementos facturables cada uno. Es una simulación basada en la tarifa pública, no un margen de caja auditado.

## 4. Cambios aplicados

- La búsqueda REST y la herramienta MCP rechazan cantidades fuera de 1–20 al precio fijo de 0.08 USDC, en lugar de aceptar hasta 50 con el mismo precio.
- El reto x402 anuncia el límite máximo de búsqueda de 20 resultados.
- El coste de scraper se estima por resultados con tarifas públicas de inicio: Clockworks principal $1.70/1.000, fallback $1.00/1.000; API Dojo $0.30/1.000 en búsqueda/perfil/comentarios; Clockworks perfil $1.00/1.000 y comentarios $0.50/1.000.
- Fallos, respuestas exitosas vacías y tarifas desconocidas ya no se contabilizan como coste cero.
- Los nuevos registros de coste y de venta incluyen request_id común derivado del fingerprint ya usado para idempotencia; venta además registra cache_hit y result_count. No se registran queries sin procesar ni firmas.
- Se añadieron pruebas para los límites, costes estimados, fallos/vacíos y correlación del ledger.

## 5. Lo que sigue faltando para saber si es rentable

1. Exportar de Apify la factura/uso facturado por actor y conciliar con src/coste_tiktok.jsonl; las páginas públicas son tarifas «desde».
2. Dejar acumular datos correlacionados nuevos y revisar para cada venta el coste del primario y de todos los fallbacks. Tratar fallos con coste desconocido como exposición, no como cero.
3. Revisar los eventos de src/metrics_tiktok.jsonl: payment_challenge, payment_rejected, payment_completed, payment_settle_failed, free_miss, pending_or_retry, server_error e http_200. Compararlos con el ledger; los eventos se agregan por ruta y estado, sin identificar usuario. Aún no miden clientes únicos, CAC, canal de adquisición ni conversión comercial completa.
4. Elegir un segmento (por ejemplo, agencias/investigadores de tendencias) y comprobar retención mediante repetición real, no solo llamadas de prueba.
5. La herramienta MCP pública todavía entrega instrucciones para llamar a REST con un cliente compatible con x402; no ejecuta ni firma el pago ella misma. Esto se documenta explícitamente y sigue siendo fricción a resolver si se quiere una experiencia MCP de una sola llamada.

## 6. Fuentes de precios consultadas

- [Clockworks TikTok Scraper](https://apify.com/clockworks/tiktok-scraper)
- [Clockworks TikTok Data Extractor / fallback](https://apify.com/clockworks/free-tiktok-scraper)
- [API Dojo search](https://apify.com/apidojo/tiktok-scraper)
- [Clockworks profile](https://apify.com/clockworks/tiktok-profile-scraper)
- [Clockworks comments](https://apify.com/clockworks/tiktok-comments-scraper)
- [API Dojo profile](https://apify.com/apidojo/tiktok-profile-scraper)
- [API Dojo comments](https://apify.com/apidojo/tiktok-comments-scraper)

Las fuentes se consultaron el 11 de octubre de 2026. Las páginas muestran precios públicos anunciados por los proveedores; no sustituyen una factura real ni garantizan que el precio efectivo de la cuenta coincida.
