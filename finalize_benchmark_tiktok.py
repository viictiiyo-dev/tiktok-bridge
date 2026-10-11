# -*- coding: utf-8 -*-
"""Recalculate benchmark stats correctly without re-running paid scraping actors."""
import csv
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent
JSON_PATH = ROOT / "BENCHMARK_TIKTOK_2026-10-11.json"
CSV_PATH = ROOT / "BENCHMARK_TIKTOK_2026-10-11.csv"
REVIEW_PATH = ROOT / "BENCHMARK_TIKTOK_REVISION_MANUAL.csv"
MD_PATH = ROOT / "BENCHMARK_TIKTOK_2026-10-11.md"

doc = json.loads(JSON_PATH.read_text(encoding="utf-8"))
queries = doc["queries"]
names = ["Clockworks principal", "Clockworks fallback", "API Dojo", "TikTok Bridge (router)"]

def get_rows(label):
    if label == "TikTok Bridge (router)":
        return [q["bridge"] for q in queries]
    return [q["providers"][label] for q in queries]

summary = {}
for label in names:
    rows = get_rows(label)
    status_list = [str(r.get("request_status", "error")) for r in rows]
    response_completed = sum(s in {"ok", "empty"} for s in status_list)
    nonempty = [r for r in rows if r.get("result_count", 0) > 0]
    errors = sum(s == "error" for s in status_list)
    empties = sum(s == "empty" for s in status_list)
    schema_all = [float(r.get("schema_completeness_pct", 0)) for r in rows]
    cover_all = [float(r.get("cover_pct", 0)) for r in rows]
    url_all = [float(r.get("url_pct", 0)) for r in rows]
    summary[label] = {
        "query_count": len(rows),
        "responses_completed": response_completed,
        "response_completion_rate_pct": round(100 * response_completed / max(1, len(rows)), 1),
        "queries_with_results": len(nonempty),
        "nonempty_query_rate_pct": round(100 * len(nonempty) / max(1, len(rows)), 1),
        "empty_responses": empties,
        "errors_timeouts": errors,
        "mean_latency_s": round(statistics.mean(float(r.get("latency_s", 0)) for r in rows), 3),
        "mean_results_all_queries": round(statistics.mean(float(r.get("result_count", 0)) for r in rows), 2),
        "mean_schema_completeness_pct": round(statistics.mean(float(r.get("schema_completeness_pct", 0)) for r in nonempty), 2) if nonempty else 0.0,
        "mean_schema_completeness_all_attempts_pct": round(statistics.mean(schema_all), 2),
        "mean_cover_pct": round(statistics.mean(float(r.get("cover_pct", 0)) for r in nonempty), 2) if nonempty else 0.0,
        "mean_cover_all_attempts_pct": round(statistics.mean(cover_all), 2),
        "mean_url_pct": round(statistics.mean(float(r.get("url_pct", 0)) for r in nonempty), 2) if nonempty else 0.0,
        "mean_url_all_attempts_pct": round(statistics.mean(url_all), 2),
        "mean_lexical_score": round(statistics.mean(float(r.get("mean_lexical_score", 0)) for r in nonempty), 3) if nonempty else 0.0,
        "mean_lexical_score_all_attempts": round(statistics.mean(float(r.get("mean_lexical_score", 0)) for r in rows), 3),
        "mean_lexical_relevant_pct": round(statistics.mean(float(r.get("lexical_relevant_at_8_pct", 0)) for r in nonempty), 2) if nonempty else 0.0,
        "total_duplicates": sum(int(r.get("duplicate_count", 0)) for r in rows),
        "mean_simulated_bridge_upstream_s": round(statistics.mean(float(q["bridge"].get("simulated_sequential_upstream_s", 0)) for q in queries), 3) if label == "TikTok Bridge (router)" else None,
        "mean_router_compute_replay_s": round(statistics.mean(float(q["bridge"].get("bridge_compute_replay_s", 0)) for q in queries), 4) if label == "TikTok Bridge (router)" else None,
        "mean_router_sources": round(statistics.mean(int(q["bridge"].get("source_count", 0)) for q in queries), 2) if label == "TikTok Bridge (router)" else None,
        "fallback_query_count": sum(bool(q["bridge"].get("fallback_used")) for q in queries) if label == "TikTok Bridge (router)" else None,
    }

doc["summary"] = summary
doc["configuration"]["aggregation_note"] = (
    "A response with zero items is counted as a completed empty response, not a request failure. "
    "Schema/cover/URL/relevance conditional averages are computed only for queries with results; "
    "all-attempt averages remain available separately."
)
JSON_PATH.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

csv_fields = [
    "query", "system", "request_status", "latency_s", "result_count", "unique_id_count",
    "duplicate_count", "schema_completeness_pct", "id_pct", "desc_pct", "author_pct",
    "likes_pct", "date_pct", "hashtags_pct", "cover_pct", "url_pct", "mean_lexical_score",
    "lexical_relevant_at_8_pct", "sources_used", "source_count", "fallback_used",
    "simulated_sequential_upstream_s", "bridge_compute_replay_s", "upstream_error",
]
with CSV_PATH.open("w", encoding="utf-8-sig", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=csv_fields, extrasaction="ignore")
    writer.writeheader()
    for q in queries:
        for label, row in q["providers"].items():
            writer.writerow({"query": q["query"], "system": label, **row})
        writer.writerow({"query": q["query"], "system": "TikTok Bridge (router)", **q["bridge"]})

md = [
    "# Benchmark TikTok Bridge — resultados en vivo",
    "",
    f"- Fecha UTC: {doc.get('generated_at_utc')}",
    f"- Consultas: {len(queries)}; máximo {doc['configuration']['max_results_per_query']} resultados por proveedor y consulta.",
    f"- Región: {doc['configuration']['region']}; timeout por actor: {doc['configuration']['per_actor_timeout_seconds']} s.",
    "- No se hicieron pagos x402. Sí se ejecutaron llamadas directas a Apify y pueden haberse generado costes; no se consultó la factura.",
    "- Bridge se evaluó reproduciendo las respuestas reales obtenidas en esta misma ronda, sin volver a pagar las mismas fuentes para comparar su política de normalización y fallback.",
    "- Una respuesta vacía es una petición completada sin resultados; un error/timeout sí es un fallo.",
    "- La relevancia lexical es una proxy basada en tokens de descripción/hashtags, no un juicio humano ni una medida semántica definitiva.",
    "",
    "## Resumen por sistema",
    "",
    "| Sistema | Respuesta HTTP útil/completada | Consultas con resultados | Errores | Resultados medios por consulta | Latencia medida / estimada | Completitud con resultados | Portada con resultados | URL con resultados | Relevancia lexical media con resultados |",
    "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
]
for label in names:
    s = summary[label]
    if label == "TikTok Bridge (router)":
        latency = f"~{s['mean_simulated_bridge_upstream_s']} s upstream modelados"
    else:
        latency = f"{s['mean_latency_s']} s directa"
    md.append(
        f"| {label} | {s['responses_completed']}/{s['query_count']} ({s['response_completion_rate_pct']}%) | "
        f"{s['queries_with_results']}/{s['query_count']} ({s['nonempty_query_rate_pct']}%) | "
        f"{s['errors_timeouts']} | {s['mean_results_all_queries']} | {latency} | "
        f"{s['mean_schema_completeness_pct']}% | {s['mean_cover_pct']}% | {s['mean_url_pct']}% | "
        f"{s['mean_lexical_score']} |"
    )
md += [
    "",
    "### Agregados adicionales",
    "",
    "| Sistema | Completitud media contando fallos/vacíos como 0 | Portada en todos los intentos | URL en todos los intentos | Media de relevancia con vacíos/fallos como 0 |",
    "|---|---:|---:|---:|---:|",
]
for label in names:
    s = summary[label]
    md.append(f"| {label} | {s['mean_schema_completeness_all_attempts_pct']}% | {s['mean_cover_all_attempts_pct']}% | {s['mean_url_all_attempts_pct']}% | {s['mean_lexical_score_all_attempts']} |")
md += [
    "",
    "## Resultados por consulta",
    "",
    "| Consulta | Sistema | Estado | n | Latencia/overhead | Esquema | Portada | URL | Relevancia lexical | Fuentes que usó Bridge |",
    "|---|---|---|---:|---:|---:|---:|---:|---:|---|",
]
for q in queries:
    for label, row in q["providers"].items():
        md.append(
            f"| {q['query']} | {label} | {row['request_status']} | {row['result_count']} | "
            f"{row['latency_s']} s | {row['schema_completeness_pct']}% | {row['cover_pct']}% | "
            f"{row['url_pct']}% | {row['mean_lexical_score']} | — |"
        )
    b = q["bridge"]
    md.append(
        f"| {q['query']} | TikTok Bridge (router) | {b['bridge_status']} | {b['result_count']} | "
        f"~{b['simulated_sequential_upstream_s']} s upstream modelados; {b['bridge_compute_replay_s']} s de overhead local | "
        f"{b['schema_completeness_pct']}% | {b['cover_pct']}% | {b['url_pct']}% | "
        f"{b['mean_lexical_score']} | {b['sources_used'] or 'ninguna'} |"
    )
md += [
    "",
    "## Lectura del resultado",
    "",
    "- Clockworks principal: 5/6 consultas con resultados; una petición agotó el timeout. En las consultas que sí devolvieron datos, la completitud media del esquema es " + f"{summary['Clockworks principal']['mean_schema_completeness_pct']}%.",
    "- Clockworks fallback: 6/6 consultas con resultados; completitud media condicional " + f"{summary['Clockworks fallback']['mean_schema_completeness_pct']}%. Su media de latencia directa incluye todos los intentos.",
    "- API Dojo: " + f"{summary['API Dojo']['responses_completed']}/6 peticiones respondieron (incluidas las vacías), " + f"{summary['API Dojo']['queries_with_results']}/6 devolvieron resultados y " + f"{summary['API Dojo']['errors_timeouts']} terminó en error/timeout. La baja tasa de respuestas con datos es un hallazgo de esta muestra, no una tasa universal.",
    "- Bridge: " + f"{summary['TikTok Bridge (router)']['queries_with_results']}/6 consultas con resultados; usó fallback en " + f"{summary['TikTok Bridge (router)']['fallback_query_count']}/6. La latencia upstream modelada es la suma de las duraciones medidas de las fuentes que el router habría consultado; no es una petición end-to-end real al endpoint HTTP.",
    "- La completitud condicional evalúa ocho campos: id, desc, autor, likes, fecha, hashtags, cover y url. Los promedios de todos los intentos se muestran aparte para no esconder fallos/vacíos.",
    "- La coincidencia lexical puede infravalorar sinónimos y sobrevalorar palabras coincidentes sin relación semántica. No declarar una victoria semántica sin evaluación humana.",
    "",
    "## Revisión manual",
    "",
    "En BENCHMARK_TIKTOK_REVISION_MANUAL.csv hay hasta cinco primeros resultados por sistema y consulta. Completa human_relevance_0_2 con 0=no relevante, 1=parcial y 2=relevante, y añade notas breves. Así se obtiene una medida real de Precision@5 y se puede comparar el ranking con la misma pauta para todos.",
    "",
    "## Archivos generados",
    "",
    "- BENCHMARK_TIKTOK_2026-10-11.json: resultados completos, respuestas y métricas.",
    "- BENCHMARK_TIKTOK_2026-10-11.csv: métricas por consulta/sistema.",
    "- BENCHMARK_TIKTOK_REVISION_MANUAL.csv: muestra para etiquetado humano.",
    "- benchmark_tiktok_bridge.py: runner reproducible; vuelve a consultar Apify y puede generar costes.",
]
MD_PATH.write_text("\n".join(md) + "\n", encoding="utf-8")
print("RECALCULATED_SUMMARY")
print(json.dumps(summary, ensure_ascii=True, indent=2))
print("UPDATED", MD_PATH, CSV_PATH, JSON_PATH)
