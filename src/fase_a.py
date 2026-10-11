"""Fase A: concilia facturado Apify por actor vs coste_tiktok.jsonl y ledger.
Token desde .env. Solo lectura. Desconocidos = exposicion, nunca cero."""
import json
import os
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
TOK = ""
for line in (BASE / ".env").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if line.startswith("APIFY_TOKEN="):
        TOK = line.split("=", 1)[1].strip()


def get(path):
    with urllib.request.urlopen("https://api.apify.com" + path, timeout=30) as r:
        return json.load(r)


runs = get(f"/v2/actor-runs?limit=100&desc=1&token={TOK}").get("data", {})
items = runs.get("items", [])
print("runs en cuenta (ult 100):", len(items), "total:", runs.get("total", "?"))

per_actor = {}
for run in items:
    actor = run.get("actId", "?")
    cost = run.get("usageTotalUsd") or 0
    per_actor.setdefault(actor, {"runs": 0, "usd": 0.0, "failed": 0})
    per_actor[actor]["runs"] += 1
    if run.get("status") == "FAILED":
        per_actor[actor]["failed"] += 1
    try:
        per_actor[actor]["usd"] += float(cost or 0)
    except (TypeError, ValueError):
        pass

print("== FACTURADO POR ACTOR (usageTotalUsd inline) ==")
for actor, d in per_actor.items():
    print(f"{actor}: {d['runs']} runs ({d['failed']} failed), billed=${d['usd']:.4f}")
    if d["runs"] and not d["usd"]:
        print("  (coste DESCONOCIDO: exposicion, no cero)")
