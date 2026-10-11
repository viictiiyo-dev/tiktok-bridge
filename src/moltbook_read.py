"""Lee 2 posts objetivo para comentar con contexto. Key desde .env."""
import json
import os
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


for pid in ["624cec01-8656-4495-8c17-a2f46d3fbf96", "db28e86f-18b4-488c-9f78-214de53167fc"]:
    p = api("/posts/" + pid).get("post", {})
    print("=" * 60)
    print("TITLE:", p.get("title"))
    print("AUTHOR:", (p.get("author") or {}).get("name"))
    print((p.get("content") or "")[:900])
