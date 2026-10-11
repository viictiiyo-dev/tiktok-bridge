# Plan de acción: rentabilidad de TikTok Bridge

Fecha de corte: 11 de octubre de 2026.

## Diagnóstico comprobado

- El ledger local tiene siete liquidaciones de 0,08 USDC cada una (0,56 USDC brutos) y una sola dirección pagadora distinta. El registro no permite atribuir con seguridad esa dirección a un cliente externo.
- El ledger de ventas antiguo no comparte identificador con la mayoría de las ejecuciones del scraper. Por tanto, los costes históricos por cliente no se pueden reconstruir de forma fiable.
- Los logs antiguos mezclan llamadas pagadas, tests y el benchmark; además, varias entradas usan costes fijos por ejecución o reflejan coste desconocido. No se deben restar en bloque a los 0,56 USDC.
- El precio público de inicio del scraper principal Clockworks es 1,70 USD/1.000 resultados; el fallback de Clockworks figura desde 1,00 USD/1.000 y API Dojo desde 0,30 USD/1.000. Son referencias, no la factura efectiva de la cuenta.
- El último benchmark probó fiabilidad de proveedor; no mide el embudo comercial, clientes externos, repetición ni CAC.

## Cambios completados en el código

1. REST y MCP rechazan búsquedas fuera de 1–20 resultados al precio fijo de 0,08 USDC. El límite previo de 50 podía producir un coste PPR teórico de 0,085 USD solo con el proveedor principal.
2. El reto x402 publica el límite máximo de 20 resultados.
3. Los logs nuevos estiman el coste según resultados y tarifas públicas de inicio; los fallos, vacíos y proveedores sin tarifa conocida quedan como desconocidos.
4. El coste de cada llamada a actor se correlaciona con la venta mediante un fingerprint de idempotencia. La venta anota el resultado de caché y cuántos elementos devolvió; no persiste la consulta ni la firma.
5. La API registra ruta, categoría de respuesta HTTP y latencia sin almacenar IP, wallet, payload ni query. La consulta de agregados queda detrás de STATS_TOKEN.
6. Se añadió examples/tiktok_bridge_x402_client.mjs para efectuar una llamada REST con el SDK x402. El script exige un consentimiento explícito por variable de entorno antes de poder pagar; no se ha ejecutado con una wallet real.
7. El auditor local reconstruye los ingresos y muestra por qué los datos históricos aún no bastan para afirmar un margen neto.

## Experimento comercial recomendado

### Fase A — conciliar coste real

Exportar del panel de Apify el consumo facturado por actor y periodo. Comparar actor por actor con src/coste_tiktok.jsonl y separar consultas con caché, primario, fallback, timeout y resultado vacío. No considerar coste desconocido como cero.

**Gate propuesto:** no escalar campañas hasta que al menos el 95 % de las consultas pagadas nuevas tengan su coste de proveedor conciliado y el margen bruto PPR sea positivo también en las consultas que activan fallback.

### Fase B — probar una propuesta de valor estrecha

Hipótesis inicial, todavía no validada: agencias pequeñas y equipos de investigación de mercado que monitorizan tendencias o identifican creadores en España. Entrevistar usuarios objetivo y probar un caso muy concreto (por ejemplo, hallar creadores de un nicho y devolver URL, engagement y señal de relevancia en un JSON limpio).

No competir solo por “scraping de TikTok”. Probar el beneficio: menor esfuerzo de integración, una respuesta con esquema consistente y recuperación automática cuando una fuente no responde.

### Fase C — observar conversión y retención

Revisar cada semana métricas por ruta y estado, pagos realmente liquidados, free_miss, coste del fallback, wallets compradoras anonimizadas y segunda compra. Los HTTP 402 cuentan desafíos, no necesariamente personas únicas; HTTP 200 tampoco demuestra un pago, porque un free_miss se devuelve sin liquidación.

Registrar manualmente el canal de adquisición en el experimento comercial (landing, comunidad, integración o recomendación). El código no puede inferir el canal solo a partir de una dirección de pago.

### Fase D — mejorar integración de pago

El MCP público sigue siendo un directorio/guía para llamar al REST con un cliente x402; no firma ni liquida por el consumidor. El ejemplo Node.js reduce la fricción del cliente REST. La siguiente mejora de integración debe implementar y probar un flujo MCP pagador end-to-end con consentimiento y límites de gasto, antes de anunciar “una sola llamada” o activar pagos automáticos.

## Criterios para decidir

- **Seguir:** usuarios externos que repiten y margen bruto conciliado positivo, incluidos fallbacks.
- **Ajustar precio o límite:** el coste facturado del percentil 95 se acerca o supera un umbral comercial interno acordado.
- **Cambiar el enfoque:** hay consultas de prueba pero no una segunda compra, o los usuarios no valoran la normalización/fallback como algo por lo que paguen.
- **No afirmar todavía:** superioridad semántica, clientes recurrentes, CAC, beneficio neto o rentabilidad global; no hay datos suficientes.

Este plan distingue los cambios hechos en el código de las hipótesis comerciales que aún requieren usuarios reales y facturación verificada.
