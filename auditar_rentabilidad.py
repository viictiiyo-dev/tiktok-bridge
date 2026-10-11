#!/usr/bin/env python3
"""Auditoría local de ingresos y costes de TikTok Bridge; no consulta APIs ni realiza pagos."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
SALES_PATH = SRC / "ventas_tiktok.jsonl"
COST_PATH = SRC / "coste_tiktok.jsonl"
PAYMENTS_DB = SRC / "payment_requests.sqlite3"
METRICS_PATH = SRC / "metrics_tiktok.jsonl"
OUT = ROOT / "AUDITORIA_RENTABILIDAD_2026-10-11.md"

PRICE_USD_PER_1000 = {
    "clockworks~tiktok-scraper": 1.70,
    "clockworks~free-tiktok-scraper": 1.00,
    "apidojo~tiktok-scraper": 0.30,
    "clockworks~tiktok-profile-scraper": 1.00,
    "apidojo~tiktok-profile-scraper": 0.30,
    "clockworks~tiktok-comments-scraper": 0.50,
    "apidojo~tiktok-comments-scraper": 0.30,
}
PRICE_URLS = [
    ("Clockworks TikTok Scraper", "https://apify.com/clockworks/tiktok-scraper"),
    ("Clockworks TikTok Data Extractor / fallback", "https://apify.com/clockworks/free-tiktok-scraper"),
    ("API Dojo search", "https://apify.com/apidojo/tiktok-scraper"),
    ("Clockworks profile", "https://apify.com/clockworks/tiktok-profile-scraper"),
    ("Clockworks comments", "https://apify.com/clockworks/tiktok-comments-scraper"),
    ("API Dojo profile", "https://apify.com/apidojo/tiktok-profile-scraper"),
    ("API Dojo comments", "https://apify.com/apidojo/tiktok-comments-scraper"),
]

def read_jsonl(path):
    rows, bad = [], 0
    if not path.exists():
        return rows, bad
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
            if isinstance(obj, dict):
                rows.append(obj)
            else:
                bad += 1
        except json.JSONDecodeError:
            bad += 1
    return rows, bad

sales, bad_sales = read_jsonl(SALES_PATH)
costs, bad_costs = read_jsonl(COST_PATH)
metrics, bad_metrics = read_jsonl(METRICS_PATH)
metric_counts = Counter((str(x.get("event", "unknown")), str(x.get("endpoint", "unknown"))) for x in metrics)
sales = [x for x in sales if x.get("settled_by_facilitator") is True]
gross_usdc = sum(int(x.get("amount", 0) or 0) / 1_000_000 for x in sales)
unique_txs = {str(x.get("tx")) for x in sales if x.get("tx")}
unique_payers = {str(x.get("payer")).lower() for x in sales if x.get("payer")}
sales_by_kind = Counter(x.get("kind", "unknown") for x in sales)
payers_masked = sorted(hashlib.sha256(p.encode()).hexdigest()[:8] for p in unique_payers)

linked_costs = defaultdict(list)
for c in costs:
    if c.get("request_id"):
        linked_costs[str(c["request_id"])].append(c)

correlated_sales = [s for s in sales if s.get("request_id")]
unlinked_sales_n = len(sales) - len(correlated_sales)
current_cost_records = [c for c in costs if c.get("cost_basis") == "published_starting_price_estimate"]
cost_ids_without_sale = set(linked_costs) - {str(s["request_id"]) for s in correlated_sales}
known_cost_without_sale = sum(
    float(c["cost_est_usd"])
    for request_id in cost_ids_without_sale
    for c in linked_costs[request_id]
    if c.get("cost_est_usd") is not None
)
unknown_attempts_without_sale = sum(
    1
    for request_id in cost_ids_without_sale
    for c in linked_costs[request_id]
    if c.get("cost_est_usd") is None
)
legacy_cost_records = [c for c in costs if c.get("cost_basis") not in {
    "published_starting_price_estimate", "failed_run_cost_unknown",
    "empty_run_cost_unknown", "provider_cost_not_verified"
}]
unknown_or_failed = [c for c in costs if c.get("cost_est_usd") is None]
estimated_current_sum = sum(float(c["cost_est_usd"]) for c in current_cost_records)

payment_states = Counter()
if PAYMENTS_DB.exists():
    try:
        with sqlite3.connect(str(PAYMENTS_DB), timeout=2) as conn:
            table = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='payment_requests'").fetchone()
            if table:
                payment_states.update(dict(conn.execute("SELECT state, COUNT(*) FROM payment_requests GROUP BY state").fetchall()))
    except sqlite3.Error:
        payment_states["database_unavailable"] += 1

def usd(value):
    return "$" + f"{value:,.6f}"

def pct(value):
    return f"{value * 100:.1f}%"

now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
lines = [
    "# Auditoría de rentabilidad — TikTok Bridge",
    "",
    f"**Generada:** {now}. Solo lee ficheros y SQLite locales; no llama a Apify, no consulta carteras ni ejecuta pagos.",
    "",
    "## 1. Ingresos realmente registrados",
    "",
    f"- Liquidaciones registradas con settled_by_facilitator=true: **{len(sales)}**.",
    f"- Ingreso bruto del ledger: **{gross_usdc:.6f} USDC** (no es beneficio neto).",
    f"- Transacciones con hash no vacío y únicos: **{len(unique_txs)}**.",
    f"- Direcciones pagadoras distintas: **{len(unique_payers)}**.",
    f"- Tipos de operación: {json.dumps(dict(sales_by_kind), ensure_ascii=False)}.",
    f"- Identificadores anonimizados de pagadores (SHA-256 prefijo; no son direcciones): {', '.join(payers_masked) or 'ninguno'}.",
    "",
    "Interpretación: el registro solo acredita un pagador distinto en la muestra local. No basta para afirmar demanda externa ni retención. No se infiere si esa dirección pertenece al operador o a un cliente.",
    "",
    "## 2. ¿Podemos calcular el margen real por venta?",
    "",
    f"- Ventas anteriores sin request_id común con el ledger de costes: **{unlinked_sales_n}/{len(sales)}**.",
    f"- Ventas con identificador correlacionable: **{len(correlated_sales)}/{len(sales)}**.",
    f"- Registros históricos de coste con esquema antiguo/no comparable: **{len(legacy_cost_records)}**.",
    f"- Registros de coste sin estimación fiable (fallo, vacío, proveedor sin tarifa verificada): **{len(unknown_or_failed)}** de {len(costs)}.",
    f"- Registros de coste con estimación PPR pública actual: **{len(current_cost_records)}**, suma estimada **{usd(estimated_current_sum)}**.",
    f"- IDs de peticiones con coste pero sin venta liquidada correlacionada: **{len(cost_ids_without_sale)}**, coste estimado conocido {usd(known_cost_without_sale)} y **{unknown_attempts_without_sale}** intentos de coste desconocido.",
    f"- Eventos HTTP instrumentados disponibles: **{len(metrics)}**. Contadores actuales: {json.dumps({str(k[0]) + ' @ ' + str(k[1]): v for k, v in metric_counts.items()}, ensure_ascii=False) if metrics else 'sin histórico; la instrumentación acaba de añadirse'}.",
    "",
    "Conclusión: no se puede reconstruir el coste de cada venta histórica porque los logs previos no compartían identificador y también incluyen pruebas/benchmark. La suma de costes del archivo no debe restarse sin más a los ingresos del ledger. Desde la nueva instrumentación, los costes de proveedor y la venta usan el mismo hash de correlación, sin guardar la consulta ni la firma de pago.",
    "",
    "## 3. Economía unitaria de búsqueda (tarifas públicas de referencia)",
    "",
    "La página de Clockworks anuncia precio desde $1.70/1.000 resultados para el scraper principal; el actor alternativo aparece desde $1.00/1.000. API Dojo anuncia $0.30/1.000 posts. Son precios públicos de referencia, no la factura verificada de esta cuenta. El cálculo es PPR sobre resultados y no cuantifica coste de fallos/vacíos, gastos ajenos al PPR, servidor ni soporte.",
    "",
    "| Escenario | Coste PPR estimado | Ingreso | Margen antes de otros gastos | Margen % |",
    "|---|---:|---:|---:|---:|",
]
for n in (10, 20, 50):
    cost = n * PRICE_USD_PER_1000["clockworks~tiktok-scraper"] / 1000
    gross_margin = 0.08 - cost
    lines.append(f"| {n} resultados, solo principal | {usd(cost)} | {usd(0.08)} | {usd(gross_margin)} | {pct(gross_margin / 0.08)} |")
n = 20
dual = n * (PRICE_USD_PER_1000["clockworks~tiktok-scraper"] + PRICE_USD_PER_1000["clockworks~free-tiktok-scraper"]) / 1000
lines.append(f"| 20 resultados desde principal + 20 desde fallback | {usd(dual)} | {usd(0.08)} | {usd(0.08-dual)} | {pct((0.08-dual)/0.08)} |")
lines.extend([
    "",
    "El límite anterior de 50 resultados podía hacer que el coste de lista del proveedor principal fuera aproximadamente $0.085, por encima del ingreso de $0.08, antes de considerar cualquier fallback. Se ha limitado la búsqueda pública y MCP a 1–20 resultados por consulta al precio actual. A 20 resultados, la comparación de PPR sola deja $0.046 de margen bruto estimado con el actor principal, pero solo $0.026 si ambos actores producen 20 elementos facturables cada uno. Es una simulación basada en la tarifa pública, no un margen de caja auditado.",
    "",
    "## 4. Cambios aplicados",
    "",
    "- La búsqueda REST y la herramienta MCP rechazan cantidades fuera de 1–20 al precio fijo de 0.08 USDC, en lugar de aceptar hasta 50 con el mismo precio.",
    "- El reto x402 anuncia el límite máximo de búsqueda de 20 resultados.",
    "- El coste de scraper se estima por resultados con tarifas públicas de inicio: Clockworks principal $1.70/1.000, fallback $1.00/1.000; API Dojo $0.30/1.000 en búsqueda/perfil/comentarios; Clockworks perfil $1.00/1.000 y comentarios $0.50/1.000.",
    "- Fallos, respuestas exitosas vacías y tarifas desconocidas ya no se contabilizan como coste cero.",
    "- Los nuevos registros de coste y de venta incluyen request_id común derivado del fingerprint ya usado para idempotencia; venta además registra cache_hit y result_count. No se registran queries sin procesar ni firmas.",
    "- Se añadieron pruebas para los límites, costes estimados, fallos/vacíos y correlación del ledger.",
    "",
    "## 5. Lo que sigue faltando para saber si es rentable",
    "",
    "1. Exportar de Apify la factura/uso facturado por actor y conciliar con src/coste_tiktok.jsonl; las páginas públicas son tarifas «desde».",
    "2. Dejar acumular datos correlacionados nuevos y revisar para cada venta el coste del primario y de todos los fallbacks. Tratar fallos con coste desconocido como exposición, no como cero.",
    "3. Revisar los eventos de src/metrics_tiktok.jsonl: payment_challenge, payment_rejected, payment_completed, payment_settle_failed, free_miss, pending_or_retry, server_error e http_200. Compararlos con el ledger; los eventos se agregan por ruta y estado, sin identificar usuario. Aún no miden clientes únicos, CAC, canal de adquisición ni conversión comercial completa.",
    "4. Elegir un segmento (por ejemplo, agencias/investigadores de tendencias) y comprobar retención mediante repetición real, no solo llamadas de prueba.",
    "5. La herramienta MCP pública todavía entrega instrucciones para llamar a REST con un cliente compatible con x402; no ejecuta ni firma el pago ella misma. Esto se documenta explícitamente y sigue siendo fricción a resolver si se quiere una experiencia MCP de una sola llamada.",
    "",
    "## 6. Fuentes de precios consultadas",
    "",
])
for name, url in PRICE_URLS:
    lines.append(f"- [{name}]({url})")
lines.extend([
    "",
    "Las fuentes se consultaron el 11 de octubre de 2026. Las páginas muestran precios públicos anunciados por los proveedores; no sustituyen una factura real ni garantizan que el precio efectivo de la cuenta coincida.",
    "",
])
OUT.write_text("\n".join(lines), encoding="utf-8")
print(f"Report written: {OUT}")
print(f"sales={len(sales)} gross_usdc={gross_usdc:.6f} unique_payers={len(unique_payers)}")
print(f"cost_rows={len(costs)} current_price_estimate_rows={len(current_cost_records)} unknown_cost_rows={len(unknown_or_failed)} legacy_rows={len(legacy_cost_records)}")
