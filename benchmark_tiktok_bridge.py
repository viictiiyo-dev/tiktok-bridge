# -*- coding: utf-8 -*-
"""Reproducible live benchmark of TikTok public-search providers and the Bridge router."""
import csv
import json
import statistics
import subprocess
import sys
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
import tiktok_router as router

RUN_DATE = datetime.now(timezone.utc).isoformat(timespec="seconds")
LIMIT = 8
TIMEOUT_S = 18
QUERIES = [
    "receta paella",
    "cafeteria madrid",
    "rutina skincare",
    "entrenamiento en casa principiantes",
    "consejos para entrevistas de trabajo",
    "viaje barato japon",
]
STOP_WORDS = {
    "de", "del", "para", "con", "en", "y", "la", "el", "las", "los", "por",
    "a", "the", "and", "for", "with", "on", "of", "to", "in", "un", "una",
    "como", "sobre", "sin", "mejores", "mejor",
}
OUT_JSON = ROOT / "BENCHMARK_TIKTOK_2026-10-11.json"
OUT_CSV = ROOT / "BENCHMARK_TIKTOK_2026-10-11.csv"
OUT_REVIEW = ROOT / "BENCHMARK_TIKTOK_REVISION_MANUAL.csv"
OUT_MD = ROOT / "BENCHMARK_TIKTOK_2026-10-11.md"


def tokenise(value):
    import re
    value = unicodedata.normalize("NFKD", str(value or "").casefold())
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return [x for x in re.findall(r"[a-z0-9]+", value)
            if len(x) > 1 and x not in STOP_WORDS]


def lexical_score(query, video):
    """Transparent lexical proxy, not human relevance."""
    terms = list(dict.fromkeys(tokenise(query)))
    text = str(video.get("desc") or "") + " " + " ".join(map(str, video.get("hashtags") or []))
    content = set(tokenise(text))
    if not terms:
        return 0.0
    return round(sum(1 for term in terms if term in content) / len(terms), 3)


def has_value(value):
    return value is not None and value != "" and value != []


def metrics(query, videos, request_status, latency_s):
    fields = ("id", "desc", "autor", "likes", "fecha", "hashtags", "cover", "url")
    n = len(videos)
    ids = [str(v.get("id") or "") for v in videos]
    scores = [lexical_score(query, v) for v in videos]
    total_slots = max(1, n * len(fields))
    present = sum(1 for v in videos for field in fields if has_value(v.get(field)))
    return {
        "request_status": request_status,
        "latency_s": round(float(latency_s), 3),
        "result_count": n,
        "unique_id_count": len({x for x in ids if x}),
        "duplicate_count": n - len({x for x in ids if x}),
        "schema_completeness_pct": round(100 * present / total_slots, 2) if n else 0.0,
        "id_pct": round(100 * sum(has_value(v.get("id")) for v in videos) / max(1, n), 2),
        "desc_pct": round(100 * sum(has_value(v.get("desc")) for v in videos) / max(1, n), 2),
        "author_pct": round(100 * sum(has_value(v.get("autor")) for v in videos) / max(1, n), 2),
        "likes_pct": round(100 * sum(v.get("likes") is not None for v in videos) / max(1, n), 2),
        "date_pct": round(100 * sum(has_value(v.get("fecha")) for v in videos) / max(1, n), 2),
        "hashtags_pct": round(100 * sum(isinstance(v.get("hashtags"), list) and all(isinstance(t, str) for t in v.get("hashtags", [])) for v in videos) / max(1, n), 2),
        "cover_pct": round(100 * sum(has_value(v.get("cover")) for v in videos) / max(1, n), 2),
        "url_pct": round(100 * sum(has_value(v.get("url")) for v in videos) / max(1, n), 2),
        "mean_lexical_score": round(statistics.mean(scores), 3) if scores else 0.0,
        "lexical_relevant_at_8_pct": round(100 * sum(sc >= 0.5 for sc in scores) / max(1, n), 2) if n else 0.0,
        "results": videos,
    }


def direct_call(actor, query, limit):
    if not actor:
        return {"items": None, "error": "actor_not_configured", "latency_s": 0.0, "request_status": "skipped", "videos": []}
    source_payload = router.build_search_input(query, limit)
    payload = router._payload_for_actor(actor, query, limit, kind="search", payload=source_payload)
    start = time.monotonic()
    items, error = router._run_sync(actor, payload, kind="search", timeout_s=TIMEOUT_S)
    elapsed = time.monotonic() - start
    if items is None:
        status, videos = "error", []
    else:
        videos = router._rank_videos(query, router.normalize_dataset(items).get("videos", []), limit)
        status = "ok" if videos else "empty"
    return {
        "items": items, "error": error or "", "latency_s": round(elapsed, 3),
        "request_status": status, "videos": videos, "payload_keys": sorted(payload.keys()),
    }


def review_rows(query, system, metric_row):
    rows = []
    for pos, video in enumerate(metric_row["results"][:5], start=1):
        rows.append({
            "query": query, "system": system, "rank": pos,
            "video_id": video.get("id", ""),
            "desc": str(video.get("desc", "")).replace("\r", " ").replace("\n", " ")[:280],
            "author": video.get("autor", ""), "likes": video.get("likes"),
            "url": video.get("url", ""), "lexical_score_0_1": lexical_score(query, video),
            "human_relevance_0_2": "", "human_notes": "",
        })
    return rows


def main():
    if not router._token():
        raise SystemExit("FATAL: APIFY_TOKEN no configurado; no se ha ejecutado ninguna consulta.")
    if not router.ACTOR_SEARCH:
        raise SystemExit("FATAL: ACTOR_SEARCH vacío.")
    systems = {
        "Clockworks principal": router.ACTOR_SEARCH,
        "Clockworks fallback": router.ACTOR_FALLBACK,
        "API Dojo": router.ACTOR_SEARCH_QUALITY_FALLBACK,
    }
    query_results = []
    all_review_rows = []
    started_all = time.monotonic()
    for index, query in enumerate(QUERIES, start=1):
        print(f"[{index}/{len(QUERIES)}] {query!r}: {len(systems)} fuentes, límite={LIMIT}, timeout={TIMEOUT_S}s", flush=True)
        datasets = {}
        provider_rows = {}
        for label, actor in systems.items():
            key = actor or ("disabled:" + label)
            if key not in datasets:
                datasets[key] = direct_call(actor, query, LIMIT)
            direct = datasets[key]
            row = metrics(query, direct.get("videos", []), direct.get("request_status", "skipped"), direct.get("latency_s", 0))
            row.update({
                "query": query, "system": label, "provider_configured": bool(actor),
                "upstream_error": direct.get("error", ""),
                "upstream_payload_keys": direct.get("payload_keys", []),
            })
            provider_rows[label] = row
            print(f"  {label}: {row['request_status']}, n={row['result_count']}, {row['latency_s']}s, cover={row['cover_pct']}%, url={row['url_pct']}%", flush=True)

        # Replay the exact live actor datasets through Bridge to avoid paying the same providers twice.
        used_actor_calls = []
        original_run_sync = router._run_sync
        original_fail_counts = dict(router._fail_count)
        def replay(actor, payload, kind="search", timeout_s=None):
            used_actor_calls.append(actor)
            direct = datasets.get(actor)
            if direct is None:
                return None, "provider_not_benchmarked"
            return direct.get("items"), direct.get("error", "")
        router._run_sync = replay
        router._fail_count.clear()
        try:
            bridge_start = time.monotonic()
            bridge_status, bridge_data = router.run_search(query, LIMIT)
            bridge_compute_s = time.monotonic() - bridge_start
        finally:
            router._run_sync = original_run_sync
            router._fail_count.clear()
            router._fail_count.update(original_fail_counts)
        bridge_videos = (bridge_data or {}).get("videos", []) if isinstance(bridge_data, dict) else []
        bridge_row = metrics(query, bridge_videos, bridge_status, bridge_compute_s)
        roles_by_actor = {}
        for label, actor in systems.items():
            if actor:
                roles_by_actor.setdefault(actor, label)
        used_roles = [roles_by_actor.get(actor, "unknown") for actor in dict.fromkeys(used_actor_calls)]
        simulated_upstream = sum(
            max(0.0, float(datasets.get(actor, {}).get("latency_s", 0.0)))
            for actor in dict.fromkeys(used_actor_calls)
        )
        bridge_row.update({
            "query": query, "system": "TikTok Bridge (router)", "bridge_status": bridge_status,
            "bridge_compute_replay_s": round(bridge_compute_s, 4),
            "simulated_sequential_upstream_s": round(simulated_upstream, 3),
            "sources_used": " > ".join(used_roles),
            "source_count": len(set(used_actor_calls)),
            "fallback_used": len(set(used_actor_calls)) > 1,
            "search_meta": (bridge_data or {}).get("search_meta", {}),
            "upstream_error": "", "upstream_payload_keys": [],
        })
        print(f"  Bridge: status={bridge_status}, n={bridge_row['result_count']}, sources={bridge_row['sources_used'] or 'none'}, simulated upstream={simulated_upstream:.2f}s", flush=True)
        query_results.append({
            "query": query, "providers": provider_rows, "bridge": bridge_row,
            "bridge_data": bridge_data,
            "provider_statuses": {label: {
                "status": datasets.get(actor, {}).get("request_status", "skipped"),
                "latency_s": datasets.get(actor, {}).get("latency_s", 0),
                "error": datasets.get(actor, {}).get("error", ""),
            } for label, actor in systems.items()},
        })
        for label, row in provider_rows.items():
            all_review_rows.extend(review_rows(query, label, row))
        all_review_rows.extend(review_rows(query, "TikTok Bridge (router)", bridge_row))

    elapsed_total = time.monotonic() - started_all
    system_names = ["Clockworks principal", "Clockworks fallback", "API Dojo", "TikTok Bridge (router)"]
    summary = {}
    for label in system_names:
        rows = [q["bridge"] for q in query_results] if label == "TikTok Bridge (router)" else [q["providers"][label] for q in query_results]
        successes = sum(row["request_status"] == "ok" for row in rows)
        summary[label] = {
            "query_count": len(rows), "completed_queries": successes,
            "completion_rate_pct": round(100 * successes / max(1, len(rows)), 1),
            "mean_latency_s": round(statistics.mean(row["latency_s"] for row in rows), 3),
            "mean_results": round(statistics.mean(row["result_count"] for row in rows), 2),
            "mean_schema_completeness_pct": round(statistics.mean(row["schema_completeness_pct"] for row in rows), 2),
            "mean_cover_pct": round(statistics.mean(row["cover_pct"] for row in rows), 2),
            "mean_url_pct": round(statistics.mean(row["url_pct"] for row in rows), 2),
            "mean_lexical_score": round(statistics.mean(row["mean_lexical_score"] for row in rows), 3),
            "mean_lexical_relevant_pct": round(statistics.mean(row["lexical_relevant_at_8_pct"] for row in rows), 2),
            "total_duplicates": sum(row["duplicate_count"] for row in rows),
            "mean_simulated_bridge_upstream_s": round(statistics.mean(q["bridge"]["simulated_sequential_upstream_s"] for q in query_results), 3) if label == "TikTok Bridge (router)" else None,
            "mean_router_sources": round(statistics.mean(q["bridge"]["source_count"] for q in query_results), 2) if label == "TikTok Bridge (router)" else None,
            "fallback_query_count": sum(bool(q["bridge"].get("fallback_used")) for q in query_results) if label == "TikTok Bridge (router)" else None,
        }
    document = {
        "title": "TikTok Bridge live benchmark", "generated_at_utc": RUN_DATE,
        "configuration": {
            "queries": QUERIES, "max_results_per_query": LIMIT,
            "per_actor_timeout_seconds": TIMEOUT_S, "region": router.PROXY_COUNTRY,
            "provider_roles": systems, "payments_made": False, "direct_apify_calls": True,
            "bridge_evaluation": "Router replay over live actor responses collected in this run; avoids duplicate actor calls.",
            "lexical_metric_caveat": "Term overlap in description and hashtags; not human-rated semantic relevance.",
            "cost_caveat": "Apify compute/proxy costs may have accrued. Exact charges were not fetched.",
            "bridge_latency_caveat": "Replay compute is local overhead only. Simulated sequential upstream latency sums measured actor latencies used by the router and is not an actual REST request measurement.",
        },
        "elapsed_total_s": round(elapsed_total, 3), "summary": summary, "queries": query_results,
    }
    OUT_JSON.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    with OUT_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        fields = [
            "query", "system", "request_status", "latency_s", "result_count", "unique_id_count",
            "duplicate_count", "schema_completeness_pct", "id_pct", "desc_pct", "author_pct",
            "likes_pct", "date_pct", "hashtags_pct", "cover_pct", "url_pct", "mean_lexical_score",
            "lexical_relevant_at_8_pct", "sources_used", "source_count", "fallback_used",
            "simulated_sequential_upstream_s", "bridge_compute_replay_s", "upstream_error",
        ]
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for query_row in query_results:
            for label, row in query_row["providers"].items():
                writer.writerow({"query": query_row["query"], "system": label, **row})
            writer.writerow({"query": query_row["query"], "system": "TikTok Bridge (router)", **query_row["bridge"]})
    with OUT_REVIEW.open("w", encoding="utf-8-sig", newline="") as f:
        fields = ["query", "system", "rank", "video_id", "desc", "author", "likes", "url",
                  "lexical_score_0_1", "human_relevance_0_2", "human_notes"]
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(all_review_rows)
    md = [
        "# Benchmark TikTok Bridge (en vivo)", "",
        f"- Fecha UTC: {RUN_DATE}",
        f"- Consultas: {len(QUERIES)}; máximo {LIMIT} resultados por proveedor/consulta.",
        f"- Región: {router.PROXY_COUNTRY}; timeout por actor: {TIMEOUT_S}s.",
        "- No se hicieron pagos x402. Sí se llamaron actores directamente mediante Apify; no se consultó la factura.",
        "- Bridge reproduce las respuestas vivas recogidas en este benchmark para evaluar normalización y fallback sin pagar dos veces la misma fuente.",
        "- Relevancia lexical = fracción de términos de consulta en descripción/hashtags; no es una evaluación semántica ni humana.", "",
        "## Resumen por sistema", "",
        "| Sistema | Consultas completadas | Latencia media directa | Resultados medios | Esquema completo | Portada | URL | Relevancia lexical |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for label in system_names:
        s = summary[label]
        md.append(f"| {label} | {s['completed_queries']}/{s['query_count']} ({s['completion_rate_pct']}%) | {s['mean_latency_s']} s | {s['mean_results']} | {s['mean_schema_completeness_pct']}% | {s['mean_cover_pct']}% | {s['mean_url_pct']}% | {s['mean_lexical_score']} |")
    md += ["", "## Resultados por consulta", "",
        "| Consulta | Sistema | Estado | n | Latencia/compute | Esquema | Portada | URL | Relevancia lexical | Fallback Bridge | Fuentes Bridge |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---|---|"]
    for qrow in query_results:
        for label, row in qrow["providers"].items():
            md.append(f"| {qrow['query']} | {label} | {row['request_status']} | {row['result_count']} | {row['latency_s']} s | {row['schema_completeness_pct']}% | {row['cover_pct']}% | {row['url_pct']}% | {row['mean_lexical_score']} | — | — |")
        b = qrow["bridge"]
        md.append(f"| {qrow['query']} | TikTok Bridge (router) | {b['bridge_status']} | {b['result_count']} | replay compute {b['bridge_compute_replay_s']} s | {b['schema_completeness_pct']}% | {b['cover_pct']}% | {b['url_pct']}% | {b['mean_lexical_score']} | {b['fallback_used']} | {b['sources_used'] or 'none'} |")
    md += ["", "## Interpretación", "",
        "- La latencia de proveedor es directa y medida en vivo.",
        "- replay compute de Bridge es el overhead local, no latencia REST real. simulated upstream es una estimación secuencial basada en latencias medidas.",
        "- La completitud usa ocho campos: id, desc, autor, likes, fecha, hashtags, cover y url.",
        "- El umbral lexical score >= 0.5 se incluye como proxy auditable, no como precisión semántica.",
        "- Usa el CSV de revisión manual para marcar 0=no relevante, 1=parcial y 2=relevante. Esa columna queda vacía hasta que una persona revise los vídeos.",
        "", "## Archivos", "",
        f"- {OUT_JSON.name}: respuestas completas y métricas.",
        f"- {OUT_CSV.name}: métricas por consulta/sistema.",
        f"- {OUT_REVIEW.name}: top 5 por consulta/sistema para revisión humana.",
        "", f"Tiempo total: {elapsed_total:.1f} s."]
    OUT_MD.write_text("\n".join(md) + "\n", encoding="utf-8")
    # Correctly distinguish empty responses from transport failures and report Bridge latency as modeled upstream.
    subprocess.run([sys.executable, str(ROOT / "finalize_benchmark_tiktok.py")], check=True)
    final_summary = json.loads(OUT_JSON.read_text(encoding="utf-8")).get("summary", {})
    print(f"BENCHMARK_DONE elapsed={elapsed_total:.1f}s", flush=True)
    for file in (OUT_JSON, OUT_CSV, OUT_REVIEW, OUT_MD):
        print(f"OUTPUT {file.name} bytes={file.stat().st_size}", flush=True)
    print("SUMMARY_JSON " + json.dumps(final_summary, ensure_ascii=True), flush=True)


if __name__ == "__main__":
    main()
