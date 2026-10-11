"""Moltbook: estado del post + home (notificaciones). Key desde .env."""
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


p = api("GET", "/posts/1fe22ec3-1817-4b1a-a721-17aa024a0c54").get("post", {})
print("verification_status:", p.get("verification_status"))
print("verification:", json.dumps(p.get("verification"))[:900])
print("upvotes:", p.get("upvotes"), "comments:", p.get("comment_count", p.get("comments_count")))
print("== HOME ==")
home = api("GET", "/home")
print(json.dumps(home, ensure_ascii=False)[:1500])
