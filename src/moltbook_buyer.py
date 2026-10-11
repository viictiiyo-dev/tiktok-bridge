"""Buyer-test Moltbook: ¿piden los agentes datos TikTok? Key desde .env."""
import json
import os
import urllib.parse
import urllib.request
from pathlib import Path

for line in (Path(__file__).resolve().parent.parent / ".env").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if line.startswith("MOLTBOOK_API_KEY="):
        os.environ.setdefault("MOLTBOOK_API_KEY", line.split("=", 1)[1].strip())

KEY = os.environ["MOLTBOOK_API_KEY"]


def api(path):
    req = urllib.request.Request("https://www.moltbook.com/api/v1" + path,
                                 headers={"Authorization": "Bearer " + KEY})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.load(r)


for q in ["tiktok data api for agents", "pay per call API no signup"]:
    d = api("/search?q=" + urllib.parse.quote(q) + "&type=posts&limit=5")
    print("==", q, "->", d.get("count"))
    for hit in d.get("results", [])[:5]:
        print("  -", hit.get("post_id"), "|", (hit.get("title") or "")[:90])
