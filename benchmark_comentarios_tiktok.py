"""Benchmark pequeño de calidad de comentarios TikTok entre actores Apify.

No guarda textos ni nombres de usuarios de comentarios. Solo persiste métricas agregadas.
Para ejecutar llamadas que pueden generar costes Apify, requiere:
  TIKTOK_COMMENTS_BENCHMARK_LIVE=YES
Máximo predeterminado: 20 comentarios por vídeo y 3 vídeos (6 ejecuciones).
"""
import csv
import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT_JSON = ROOT / "BENCHMARK_COMENTARIOS_TIKTOK_2026-10-11.json"
OUT_CSV = ROOT / "BENCHMARK_COMENTARIOS_TIKTOK_2026-10-11.csv"
OUT_MD = ROOT / "BENCHMARK_COMENTARIOS_TIKTOK_2026-10-11.md"
MAX_COMMENTS = max(1, min(20, int(os.environ.get("TIKTOK_COMMENTS_BENCHMARK_MAX", "20"))))
TIMEOUT = 25
VIDEOS = [
    {"label": "paella", "url": "https://www.tiktok.com/@alessandra_anez/video/7494665719724952838", "reported_comments": 290},
    {"label": "cafeteria", "url": "https://www.tiktok.com/@carlotaadiazz/video/7475301354374728982", "reported_comments": 167},
    {"label": "skincare", "url": "https://www.tiktok.com/@its.bellido/video/7593447778580221206", "reported_comments": 373},
]
ACTORS = [
    ("Clockworks principal", "clockworks~tiktok-comments-scraper", "clockworks"),
    ("API Dojo fallback", "apidojo~tiktok-comments-scraper", "apidojo"),
]
FIELDS = {
    "text": ("text", "comment", "commentText"),
    "author": ("uniqueId", "username", "author", "user.username", "user.uniqueId", "authorMeta.uniqueId"),
    "id": ("id", "commentId", "cid"),
    "date": ("createdAt", "createTimeISO", "createTime", "timestamp"),
    "likes": ("diggCount", "likes", "likeCount"),
    "replies": ("replyCount", "repliesCount"),
}

def load_env_file():
    path = ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

def get_path(obj, path):
    cur = obj
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur

def first(obj, keys):
    for key in keys:
        value = get_path(obj, key)
        if value not in (None, "", [], {}):
            return value
    return None

def call_actor(token, actor, provider, url):
    if provider == "clockworks":
        payload = {
            "postURLs": [url],
            "commentsPerPost": MAX_COMMENTS,
            "maxRepliesPerComment": 0,
            "resultsPerPage": MAX_COMMENTS,
        }
    else:
        payload = {"startUrls": [url], "maxItems": MAX_COMMENTS, "includeReplies": False}
    api_url = "https://api.apify.com/v2/acts/" + urllib.parse.quote(actor, safe="~") + \
              "/run-sync-get-dataset-items?timeout=" + str(TIMEOUT)
    request = urllib.request.Request(
        api_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json",
                 "Authorization": "Bearer " + token},
        method="POST",
    )
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT + 7) as response:
            data = json.load(response)
        elapsed = round(time.monotonic() - started, 3)
        if not isinstance(data, list):
            return [], elapsed, "invalid_dataset"
        return data, elapsed, ""
    except urllib.error.HTTPError as exc:
        return [], round(time.monotonic() - started, 3), "http_" + str(exc.code)
    except Exception as exc:
        # No guardamos URLs, tokens ni textos de excepción que pudieran incluir datos de petición.
        return [], round(time.monotonic() - started, 3), type(exc).__name__

def analyse(items, elapsed, error, video, actor_label):
    rows = [x for x in items if isinstance(x, dict) and first(x, FIELDS["text"])]
    identities = []
    for row in rows:
        cid = first(row, FIELDS["id"])
        txt = str(first(row, FIELDS["text"]) or "").strip()
        # Hash local del texto para detectar duplicados sin guardar el texto en los artefactos.
        identity = "id:" + str(cid) if cid else "text:" + hashlib.sha256(txt.casefold().encode("utf-8")).hexdigest()
        identities.append(identity)
    unique_count = len(set(identities))
    result = {
        "video": video["label"],
        "video_reported_comments": video["reported_comments"],
        "provider": actor_label,
        "requested": MAX_COMMENTS,
        "dataset_rows": len(items),
        "usable_comments": len(rows),
        "unique_comments": unique_count,
        "duplicate_comments": max(0, len(rows) - unique_count),
        "unique_pct": round(100 * unique_count / len(rows), 1) if rows else 0.0,
        "text_pct": round(100 * sum(bool(first(x, FIELDS["text"])) for x in rows) / len(rows), 1) if rows else 0.0,
        "author_pct": round(100 * sum(bool(first(x, FIELDS["author"])) for x in rows) / len(rows), 1) if rows else 0.0,
        "id_pct": round(100 * sum(bool(first(x, FIELDS["id"])) for x in rows) / len(rows), 1) if rows else 0.0,
        "date_pct": round(100 * sum(bool(first(x, FIELDS["date"])) for x in rows) / len(rows), 1) if rows else 0.0,
        "likes_pct": round(100 * sum(first(x, FIELDS["likes"]) is not None for x in rows) / len(rows), 1) if rows else 0.0,
        "replies_pct": round(100 * sum(first(x, FIELDS["replies"]) is not None for x in rows) / len(rows), 1) if rows else 0.0,
        "latency_seconds": elapsed,
        "error": error,
        "invoice_cost": "not_checked",
    }
    return result

def main():
    load_env_file()
    if os.environ.get("TIKTOK_COMMENTS_BENCHMARK_LIVE") != "YES":
        raise SystemExit("Bloqueado: define TIKTOK_COMMENTS_BENCHMARK_LIVE=YES para autorizar llamadas Apify con posible coste.")
    token = os.environ.get("APIFY_TOKEN", "").strip()
    if not token:
        raise SystemExit("APIFY_TOKEN no está configurado.")
    records = []
    for video in VIDEOS:
        for actor_label, actor, provider in ACTORS:
            print(f"Consultando {video['label']} con {actor_label} (máximo {MAX_COMMENTS})...", flush=True)
            items, elapsed, error = call_actor(token, actor, provider, video["url"])
            records.append(analyse(items, elapsed, error, video, actor_label))
            # Pausa pequeña para evitar ráfagas; no reintenta fallos ni aumenta el coste.
            time.sleep(1)
    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "videos": len(VIDEOS),
        "actors": len(ACTORS),
        "max_comments_per_video_actor": MAX_COMMENTS,
        "calls": len(records),
        "payments_x402_made": False,
        "apify_invoice_checked": False,
        "privacy": "No se guardan textos, IDs de comentarios ni nombres de usuarios; solo métricas agregadas.",
        "results": records,
    }
    OUT_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    with OUT_CSV.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(records[0].keys()))
        writer.writeheader()
        writer.writerows(records)
    lines = [
        "# Benchmark de comentarios TikTok",
        "",
        f"- Fecha UTC: {summary['generated_at_utc']}",
        f"- Vídeos: {len(VIDEOS)}; proveedores: {len(ACTORS)}; llamadas: {len(records)}",
        f"- Máximo solicitado: {MAX_COMMENTS} comentarios por vídeo/proveedor",
        "- No se realizaron pagos x402. Las llamadas directas a Apify pueden generar costes.",
        "- No se consultó la factura real; el coste final permanece sin verificar.",
        "- No se guardan textos, IDs de comentarios ni nombres de usuarios.",
        "",
        "| Vídeo | Proveedor | Útiles | Únicos | Duplicados | Autor % | ID % | Fecha % | Likes % | Latencia s | Error |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for r in records:
        lines.append(f"| {r['video']} | {r['provider']} | {r['usable_comments']} | {r['unique_comments']} | {r['duplicate_comments']} | {r['author_pct']} | {r['id_pct']} | {r['date_pct']} | {r['likes_pct']} | {r['latency_seconds']} | {r['error'] or '—'} |")
    lines += [
        "",
        "## Límites de interpretación",
        "",
        "El contador público de comentarios del vídeo no es una verdad de referencia para los comentarios recuperables: puede incluir respuestas, elementos moderados, eliminados o inaccesibles. Esta prueba compara hasta 20 comentarios por proveedor y vídeo; no demuestra exhaustividad ni calidad de todos los comentarios.",
        "",
        "La métrica de unicidad usa ID de comentario cuando existe; si falta, utiliza un hash efímero del texto para detectar duplicados. No se persiste el texto ni el hash.",
    ]
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Generados:")
    print(OUT_MD.name)
    print(OUT_CSV.name)
    print(OUT_JSON.name)
    for r in records:
        print(f"{r['video']} | {r['provider']} | usable={r['usable_comments']} | unique={r['unique_comments']} | latency={r['latency_seconds']}s | error={r['error'] or '-'}")

if __name__ == "__main__":
    main()
