"""Moltbook reglas + info submolts objetivo. Key desde .env."""
import json
import os
import urllib.request
from pathlib import Path

for line in (Path(__file__).resolve().parent.parent / ".env").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if line.startswith("MOLTBOOK_API_KEY="):
        os.environ.setdefault("MOLTBOOK_API_KEY", line.split("=", 1)[1].strip())

KEY = os.environ["MOLTBOOK_API_KEY"]
BASE = "https://www.moltbook.com/api/v1"


def api(method, path, body=None):
    req = urllib.request.Request(BASE + path, method=method,
                                 data=json.dumps(body).encode() if body else None,
                                 headers={"Authorization": "Bearer " + KEY,
                                          "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.load(r)


print("== RULES (primeros 2500 chars) ==")
rules = urllib.request.urlopen("https://www.moltbook.com/rules.md", timeout=25).read().decode("utf-8", "replace")
print(rules[:2500])
for sm in ["tooling", "builds", "agents", "infrastructure", "general"]:
    try:
        info = api("GET", "/submolts/" + sm)
        d = info.get("submolt", info)
        print(f"-- {sm}: allow_crypto={d.get('allow_crypto')} subs={d.get('subscriber_count', d.get('subscribers', '?'))} desc={(d.get('description') or '')[:100]}")
    except Exception as e:
        print(f"-- {sm}: ERR {str(e)[:120]}")
