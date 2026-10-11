"""Moltbook recon: quién soy, estado, submolts y feed. Key desde .env, jamás impresa."""
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


print("== ME ==")
print(json.dumps(api("GET", "/agents/me"), ensure_ascii=False)[:600])
print("== STATUS ==")
print(api("GET", "/agents/status"))
print("== SUBMOLTS ==")
subs = api("GET", "/submolts")
items = subs.get("submolts") or subs.get("data") or []
for s in (items if isinstance(items, list) else [])[:20]:
    print("-", s.get("name"), "|", (s.get("display_name") or "")[:50])
print("== FEED NEW ==")
feed = api("GET", "/posts?sort=new&limit=8")
posts = feed.get("posts") or feed.get("data") or []
for p in (posts if isinstance(posts, list) else []):
    print("-", (p.get("submolt") or {}).get("name") if isinstance(p.get("submolt"), dict) else p.get("submolt"),
          "|", (p.get("title") or "")[:80])
