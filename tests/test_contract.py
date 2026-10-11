import sys
import json
import os
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fastapi.testclient import TestClient

import server_v1 as s
import tiktok_router as r
import paywall as p

# Runtime metrics emitted by endpoint tests are isolated from production project logs.
s.METRICS_PATH = Path(tempfile.gettempdir()) / f"tiktok_bridge_test_metrics_{os.getpid()}.jsonl"
client = TestClient(s.app)


def setup_function(_):
    s._RATE_IP.clear()
    s._RATE_WALLET.clear()
    s._RATE_LAST_SWEEP = 0.0


def test_health():
    assert client.get("/health").json()["status"] == "ok"


def test_openapi_paths():
    paths = client.get("/openapi.json").json()["paths"]
    for expected in ("/v1/tiktok/search", "/v1/tiktok/perfil", "/v1/tiktok/comments",
                     "/health", "/llms.txt", "/skill.md"):
        assert expected in paths, expected
    assert client.get("/terms").status_code == 200  # include_in_schema=False a propósito


def test_402_con_ejemplo():
    res = client.post("/v1/tiktok/search", json={"q": "paella"})
    assert res.status_code == 402
    body = res.json()
    assert body["x402Version"] == 2
    assert body["price"] == "0.08 USDC"
    assert "videos" in body["output"]["example"]
    assert body["accepts"][0]["network"] == "eip155:8453"


def test_400s():
    # Sin firma SIEMPRE 402 aunque el body venga vacío (validador CDP + sonda Bazaar).
    for route, payload in (("/v1/tiktok/search", {}), ("/v1/tiktok/perfil", {}),
                           ("/v1/tiktok/comments", {})):
        res = client.post(route, json=payload)
        assert res.status_code == 402
        assert "payment-required" in res.headers


def test_normalize_y_freemiss():
    full = r.normalize_dataset([{"id": "1", "desc": "x" * 500, "author": {"uniqueId": "@a"},
                                 "stats": {"diggCount": 7}}])
    assert full["free_miss"] is False
    assert len(full["videos"][0]["desc"]) <= 280
    assert r.normalize_dataset([]) == {"videos": [], "free_miss": True}


def test_paywall_rechaza_firma_mala():
    import base64
    import json as _json
    bad = base64.b64encode(_json.dumps({"payload": {"signature": "x"}}).encode()).decode()
    ok, _ = p.structural_ok(bad, "search")
    assert ok is False
    assert set(p.PRICE.values()) == {"80000", "80000", "50000"}


def test_paid_sin_token_no_es_500():
    # Firma basura → 402 estructural (el gate funciona); el flujo pago real
    # se prueba en 6.2 contra mainnet. Nunca 500 ante firma inválida.
    res = client.post("/v1/tiktok/search", json={"q": "paella", "max": 2},
                      headers={"PAYMENT-SIGNATURE": "test"})
    assert res.status_code == 402
    assert "payment-required" in res.headers  # spec v2: el cliente oficial solo lee el header
    assert "reason" in res.json() or "error" in res.json()

def test_rate_limiter_bounds_unique_keys():
    bucket = {}
    for i in range(s._RATE_MAX_KEYS + 250):
        s._hit(bucket, f"unique-{i}", 30)
    assert len(bucket) <= s._RATE_MAX_KEYS


def test_structural_ok_rejects_malformed_nested_payload():
    import base64
    import json
    malformed = base64.b64encode(json.dumps({"payload": "not-an-object"}).encode()).decode()
    ok, reason = p.structural_ok(malformed, "search")
    assert ok is False
    assert "malformado" in reason


def test_seen_tx_corruption_is_quarantined(tmp_path, monkeypatch):
    path = tmp_path / "seen_tx.json"
    path.write_text("{broken", encoding="utf-8")
    monkeypatch.setattr(p, "SEEN_PATH", path)
    assert p._seen() == set()
    assert not path.exists()
    assert list(tmp_path.glob("seen_tx.json.corrupt-*"))


def test_payment_request_journal_persists_completed_response(tmp_path, monkeypatch):
    monkeypatch.setattr(p, "REQUESTS_PATH", tmp_path / "payment_requests.sqlite3")
    signature = "signature-fingerprint-test"
    key, state, saved = p.begin_payment_request(signature)
    assert state == "new"
    assert saved is None
    p.complete_payment_request(key, {"q": "paella", "videos": [{"id": "1"}]}, "receipt")
    key2, state2, saved2 = p.begin_payment_request(signature)
    assert key2 == key
    assert state2 == "completed"
    assert saved2["response_body"]["q"] == "paella"
    assert saved2["payment_response"] == "receipt"


def test_valid_payment_signature_replay_never_settles_twice(tmp_path, monkeypatch):
    import asyncio
    import base64
    import json
    import cache as cache_module
    import tiktok_router as router_module

    monkeypatch.setattr(p, "REQUESTS_PATH", tmp_path / "payment_requests.sqlite3")
    monkeypatch.setattr(p, "SALES_PATH", tmp_path / "ventas.jsonl")
    monkeypatch.setattr(p, "SEEN_PATH", tmp_path / "seen_tx.json")
    monkeypatch.setattr(p, "structural_ok", lambda _sig, _kind: (True, "test"))
    calls = []

    def facilitator(path, payload, requirements):
        calls.append(path)
        if path == "/verify":
            return {"isValid": True}
        return {"success": True, "receipt": {"transactionHash": "0x" + "a" * 64}}

    monkeypatch.setattr(p, "facilitator_call_cdp", facilitator)
    monkeypatch.setattr(cache_module, "get", lambda _key: asyncio.sleep(0, result=None))
    monkeypatch.setattr(cache_module, "put", lambda _key, _value: asyncio.sleep(0, result=True))
    router_calls = []
    monkeypatch.setattr(
        router_module, "run_search",
        lambda q, limit: (
            router_calls.append((q, limit)) or "ok",
            {"videos": [{"id": "1", "desc": "test"}], "free_miss": False},
        ),
    )
    sig_payload = {"payload": {"signature": "x", "authorization": {"from": "0xabc"}}}
    signature = base64.b64encode(json.dumps(sig_payload).encode()).decode()
    headers = {"PAYMENT-SIGNATURE": signature}

    first = client.post("/v1/tiktok/search", json={"q": "paella", "max": 2}, headers=headers)
    second = client.post("/v1/tiktok/search", json={"q": "paella", "max": 2}, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.headers.get("x-idempotent-replay") == "true"
    assert second.headers.get("payment-response") == first.headers.get("payment-response")
    assert calls.count("/settle") == 1
    assert calls.count("/verify") == 2
    assert len(router_calls) == 1


def test_mcp_public_search_is_payment_gated_by_default(monkeypatch):
    import json
    import mcp_server
    monkeypatch.setenv("MCP_ALLOW_FREE_SEARCH", "0")
    result = json.loads(mcp_server.tiktok_search("paella", 3))
    assert result["payment_required"] is True
    assert result["price"] == "0.08 USDC"
    assert result["body"] == {"q": "paella", "max": 3}

def test_profile_router_uses_public_actor_and_normalizes_output(monkeypatch):
    import tiktok_router as r
    seen = {}
    raw = [{
        "id": "123", "text": "new video", "createTimeISO": "2026-10-10T10:00:00Z",
        "authorMeta": {"name": "cocina_es", "nickName": "Cocina", "signature": "Recetas",
                       "fans": 12345},
        "diggCount": 55,
    }]

    def fake_run(actor, payload, kind="search"):
        seen["actor"] = actor
        seen["payload"] = payload
        seen["kind"] = kind
        return raw, ""

    monkeypatch.setattr(r, "_run_sync", fake_run)
    status, result = r.run_profile("@cocina_es")
    assert status == "ok"
    assert seen["kind"] == "perfil"
    assert seen["payload"]["profiles"] == ["cocina_es"]
    assert result["user"] == "cocina_es"
    assert result["bio"] == "Recetas"
    assert result["followers"] == 12345
    assert result["ultimos"][0]["id"] == "123"


def test_comments_router_validates_urls_and_normalizes_comments(monkeypatch):
    import tiktok_router as r
    seen = {}
    def fake_run(actor, payload, kind="search"):
        seen["actor"] = actor
        seen["payload"] = payload
        seen["kind"] = kind
        return [{"text": "Buen video", "uniqueId": "fan", "diggCount": 7}], ""

    monkeypatch.setattr(r, "_run_sync", fake_run)
    status, result = r.run_comments("7635981647359380758", 10)
    assert status == "ok"
    assert seen["kind"] == "comments"
    assert seen["payload"]["commentsPerPost"] == 10
    assert "/video/7635981647359380758" in seen["payload"]["postURLs"][0]
    comment = result["comments"][0]
    assert comment["autor"] == "fan"
    assert comment["autor_usuario"] == "fan"
    assert comment["texto"] == "Buen video"
    assert comment["likes"] == 7
    assert comment["respuestas"] is None
    assert comment["fecha"] == ""
    assert result["comments_meta"]["requested_count"] == 10
    assert result["comments_meta"]["returned_count"] == 1
    assert result["comments_meta"]["source_used"] == "primary"
    assert result["comments_meta"]["exhaustive"] is False
    assert result["comments_meta"]["requested_count"] == 10
    assert result["comments_meta"]["returned_count"] == 1
    assert result["comments_meta"]["source_used"] == "primary"
    assert result["comments_meta"]["exhaustive"] is False

    status, result = r.run_comments("https://evil.example/video/1234567890", 10)
    assert status == "invalid"
    assert "invalido" in result["error"]


def test_paid_profile_and_comments_use_shared_x402_flow_with_mocked_backends(tmp_path, monkeypatch):
    import asyncio
    import base64
    import json
    import cache as cache_module
    import tiktok_router as router_module

    monkeypatch.setattr(p, "REQUESTS_PATH", tmp_path / "payment_requests.sqlite3")
    monkeypatch.setattr(p, "SALES_PATH", tmp_path / "ventas.jsonl")
    monkeypatch.setattr(p, "SEEN_PATH", tmp_path / "seen_tx.json")
    monkeypatch.setattr(p, "structural_ok", lambda _sig, _kind: (True, "test"))
    facilitator_calls = []

    def facilitator(path, payload, requirements):
        facilitator_calls.append(path)
        if path == "/verify":
            return {"isValid": True}
        return {"success": True, "receipt": {"transactionHash": "0x" + format(len(facilitator_calls), "064x")}}

    monkeypatch.setattr(p, "facilitator_call_cdp", facilitator)
    monkeypatch.setattr(cache_module, "get", lambda _key: asyncio.sleep(0, result=None))
    monkeypatch.setattr(cache_module, "put", lambda _key, _value: asyncio.sleep(0, result=True))
    monkeypatch.setattr(router_module, "run_profile", lambda user: (
        "ok", {"user": user, "bio": "Recetas", "followers": 10, "ultimos": [{"id": "v1"}], "free_miss": False}
    ))
    monkeypatch.setattr(router_module, "run_comments", lambda video_id, limit: (
        "ok", {"id": video_id, "comments": [{"autor": "fan", "texto": "Hola", "likes": 1}], "free_miss": False}
    ))
    profile_sig = base64.b64encode(json.dumps({"payload": {"signature": "x", "authorization": {"from": "0xabc"}}}).encode()).decode()
    comments_sig = base64.b64encode(json.dumps({"payload": {"signature": "y", "authorization": {"from": "0xabc"}}}).encode()).decode()

    profile = client.post("/v1/tiktok/perfil", json={"user": "cocina_es"}, headers={"PAYMENT-SIGNATURE": profile_sig})
    comments = client.post("/v1/tiktok/comments", json={"id": "7635981647359380758", "max": 10},
                           headers={"PAYMENT-SIGNATURE": comments_sig})

    assert profile.status_code == 200
    assert profile.json()["bio"] == "Recetas"
    assert comments.status_code == 200
    assert comments.json()["comments"][0]["texto"] == "Hola"
    assert facilitator_calls.count("/settle") == 2


def test_profile_and_comments_still_return_402_without_signature():
    profile = client.post("/v1/tiktok/perfil", json={})
    comments = client.post("/v1/tiktok/comments", json={})
    assert profile.status_code == 402
    assert comments.status_code == 402
    assert profile.headers.get("payment-required")
    assert comments.headers.get("payment-required")


# --- Quality, reliability and integration regressions ---

def test_normalize_clockworks_real_shape_includes_cover_url_tags_and_metrics():
    raw = [{
        "id": "7494665719724952838",
        "text": "Receta de paella valenciana",
        "createTime": 1744987849,
        "createTimeISO": "2025-04-18T12:10:49Z",
        "authorMeta": {"uniqueId": "cocina_es", "name": "Cocina ES"},
        "diggCount": 22400,
        "playCount": 90000,
        "commentCount": 321,
        "shareCount": 98,
        "collectCount": 40,
        "hashtags": [{"name": "paella"}, {"hashtagName": "receta"}, {"name": "paella"}],
        "videoMeta": {"coverUrl": "https://example.test/cover.jpg", "duration": 42},
        "webVideoUrl": "https://www.tiktok.com/@cocina_es/video/7494665719724952838",
        "textLanguage": "spa",
        "isAd": False,
    }]
    out = r.normalize_dataset(raw)
    assert out["free_miss"] is False
    video = out["videos"][0]
    assert video["cover"] == "https://example.test/cover.jpg"
    assert video["url"].endswith("/video/7494665719724952838")
    assert video["hashtags"] == ["paella", "receta"]
    assert video["likes"] == 22400
    assert video["views"] == 90000
    assert video["comments"] == 321
    assert video["shares"] == 98
    assert video["saves"] == 40
    assert video["fecha"] == "2025-04-18T12:10:49Z"
    assert video["duration"] == 42
    assert video["autor_usuario"] == "cocina_es"
    assert video["is_ad"] is False


def test_normalize_apidojo_shape_and_iso_date_are_stable():
    out = r.normalize_dataset([{
        "id": "123456789",
        "title": "Cafeterias Madrid",
        "channel": {"username": "cafes_madrid", "name": "Cafés Madrid"},
        "likes": 3400,
        "views": 12000,
        "comments": 120,
        "uploadedAt": "2026-10-05T20:01:37.000Z",
        "hashtags": ["madrid", "#cafeteria"],
        "video": {"coverUrl": "https://example.test/cover.webp"},
        "postPage": {"url": "https://www.tiktok.com/@cafes_madrid/video/123456789"},
    }])
    v = out["videos"][0]
    assert v["fecha"] == "2026-10-05T20:01:37Z"
    assert v["autor"] == "cafes_madrid"
    assert v["hashtags"] == ["madrid", "cafeteria"]
    assert v["cover"] == "https://example.test/cover.webp"
    assert v["url"].endswith("/video/123456789")


def test_normalize_drops_missing_ids_and_deduplicates():
    out = r.normalize_dataset([
        {"text": "no usable id"},
        {"id": "1", "text": "paella"},
        {"id": "1", "text": "duplicate"},
    ])
    assert len(out["videos"]) == 1
    assert out["videos"][0]["desc"] == "paella"


def test_apidojo_uses_its_own_input_contract():
    payload = r._payload_for_actor("apidojo~tiktok-scraper", "cafeteria madrid", 10)
    assert payload["keywords"] == ["cafeteria madrid"]
    assert payload["maxItems"] == 10
    assert payload["location"] == r.PROXY_COUNTRY
    assert payload["sortType"] == "RELEVANCE"
    assert "searchQueries" not in payload


def test_search_cache_keys_are_canonical_and_versioned():
    assert r.search_cache_key("  Paella   Valenciana ", 10) == r.search_cache_key("paella valenciana", 10)
    assert r.search_cache_key("paella", 10) != r.search_cache_key("paella", 20)
    assert r.search_cache_key("paella", 10).startswith("tiktok:v2:search:")
    assert r.profile_cache_key("@cocina_es") == r.profile_cache_key("cocina_es")
    assert r.comments_cache_key("7635981647359380758", 20) == r.comments_cache_key(
        "https://www.tiktok.com/@user/video/7635981647359380758", 20
    )


def test_rank_videos_merges_missing_fields_and_sorts_relevant_first():
    merged = r._rank_videos("receta paella", [
        {"id": "1", "desc": "vídeo de cocina", "hashtags": [], "cover": ""},
        {"id": "1", "desc": "Receta de paella", "hashtags": ["paella"], "cover": "https://x.test/a.jpg"},
        {"id": "2", "desc": "gatos divertidos", "hashtags": []},
    ], 10)
    assert [v["id"] for v in merged][0] == "1"
    first = next(v for v in merged if v["id"] == "1")
    assert first["cover"] == "https://x.test/a.jpg"
    assert first["relevancia"] == 1.0
    assert len([v for v in merged if v["id"] == "1"]) == 1


def test_search_tries_fallback_when_primary_is_empty_and_merges(monkeypatch):
    monkeypatch.setattr(r, "ACTOR_SEARCH", "primary")
    monkeypatch.setattr(r, "ACTOR_FALLBACK", "sibling")
    monkeypatch.setattr(r, "ACTOR_SEARCH_QUALITY_FALLBACK", "apidojo~tiktok-scraper")
    monkeypatch.setattr(r, "SEARCH_BUDGET_S", 48)
    monkeypatch.setattr(r, "SYNC_TIMEOUT_S", 5)
    calls = []

    def fake_run(actor, payload, kind="search", timeout_s=None):
        calls.append((actor, payload, kind, timeout_s))
        if actor == "primary":
            return [], ""
        if actor == "sibling":
            return [
                {"id": "10", "text": "Receta de paella valenciana", "authorMeta": {"uniqueId": "a"}},
                {"id": "11", "text": "Paella rápida", "authorMeta": {"uniqueId": "b"}},
                {"id": "12", "text": "Receta paella de marisco", "authorMeta": {"uniqueId": "c"}},
            ], ""
        if actor == "apidojo~tiktok-scraper":
            return [
                {"id": "10", "text": "Receta de paella", "likes": 10,
                 "videoMeta": {"coverUrl": "https://x.test/10.jpg"},
                 "webVideoUrl": "https://www.tiktok.com/@a/video/10",
                 "hashtags": ["receta", "paella"]},
                {"id": "13", "text": "Receta de paella con marisco", "likes": 3,
                 "videoMeta": {"coverUrl": "https://x.test/13.jpg"},
                 "webVideoUrl": "https://www.tiktok.com/@c/video/13",
                 "hashtags": ["paella"]},
            ], ""
        raise AssertionError("Actor inesperado")

    monkeypatch.setattr(r, "_run_sync", fake_run)
    status, data = r.run_search("receta paella", 10)
    assert status == "ok"
    assert len(data["videos"]) == 4
    assert data["videos"][0]["relevancia"] >= data["videos"][-1]["relevancia"]
    assert [c[0] for c in calls] == ["primary", "sibling", "apidojo~tiktok-scraper"]
    assert calls[-1][1]["keywords"] == ["receta paella"]
    merged = next(v for v in data["videos"] if v["id"] == "10")
    assert merged["cover"] == "https://x.test/10.jpg"
    assert merged["url"] == "https://www.tiktok.com/@a/video/10"
    assert all(c[3] is not None for c in calls)


def test_search_falls_back_on_low_relevance_and_deduplicates(monkeypatch):
    monkeypatch.setattr(r, "ACTOR_SEARCH", "primary")
    monkeypatch.setattr(r, "ACTOR_FALLBACK", "sibling")
    monkeypatch.setattr(r, "ACTOR_SEARCH_QUALITY_FALLBACK", "")
    monkeypatch.setattr(r, "SEARCH_BUDGET_S", 48)
    monkeypatch.setattr(r, "SYNC_TIMEOUT_S", 5)
    calls = []

    def fake_run(actor, payload, kind="search", timeout_s=None):
        calls.append(actor)
        if actor == "primary":
            return [{"id": str(i), "text": "videos de gatos"} for i in range(1, 11)], ""
        return [
            {"id": "1", "text": "Receta de paella", "hashtags": [{"name": "paella"}], "videoMeta": {"coverUrl": "https://x.test/1.jpg"}},
            {"id": "20", "text": "Receta de paella de marisco"},
            {"id": "21", "text": "Paella valenciana paso a paso"},
        ], ""

    monkeypatch.setattr(r, "_run_sync", fake_run)
    status, data = r.run_search("receta paella", 10)
    assert status == "ok"
    assert calls == ["primary", "sibling"]
    assert data["videos"][0]["id"] == "1"
    assert data["videos"][0]["cover"] == "https://x.test/1.jpg"
    assert len({v["id"] for v in data["videos"]}) == len(data["videos"])


def test_search_returns_retry_if_every_provider_fails(monkeypatch):
    monkeypatch.setattr(r, "ACTOR_SEARCH", "primary")
    monkeypatch.setattr(r, "ACTOR_FALLBACK", "sibling")
    monkeypatch.setattr(r, "ACTOR_SEARCH_QUALITY_FALLBACK", "apidojo~tiktok-scraper")
    monkeypatch.setattr(r, "SEARCH_BUDGET_S", 48)
    monkeypatch.setattr(r, "SYNC_TIMEOUT_S", 5)
    calls = []

    def fail(actor, payload, kind="search", timeout_s=None):
        calls.append(actor)
        return None, "HTTP503"

    monkeypatch.setattr(r, "_run_sync", fail)
    status, data = r.run_search("paella", 10)
    assert status == "retry"
    assert data["retry_after_seconds"] == 60
    assert data["backend_error"] == "HTTP503"
    assert len(calls) == 3
    assert "actorId" not in json.dumps(data)


def test_profile_uses_optional_fallback_on_empty_result(monkeypatch):
    monkeypatch.setattr(r, "ACTOR_PROFILE", "profile-primary")
    monkeypatch.setattr(r, "ACTOR_PROFILE_FALLBACK", "profile-secondary")
    calls = []

    def fake_run(actor, payload, kind="search", timeout_s=None):
        calls.append(actor)
        if actor == "profile-primary":
            return [], ""
        return [{
            "id": "1", "text": "video reciente",
            "authorMeta": {"uniqueId": "cocina_es", "signature": "Recetas", "fans": 123}
        }], ""

    monkeypatch.setattr(r, "_run_sync", fake_run)
    status, profile = r.run_profile("cocina_es")
    assert status == "ok"
    assert calls == ["profile-primary", "profile-secondary"]
    assert profile["followers"] == 123
    assert profile["ultimos"][0]["url"] == ""


def test_comments_uses_optional_fallback_on_empty_result(monkeypatch):
    monkeypatch.setattr(r, "ACTOR_COMMENTS", "comments-primary")
    monkeypatch.setattr(r, "ACTOR_COMMENTS_FALLBACK", "comments-secondary")
    calls = []

    def fake_run(actor, payload, kind="search", timeout_s=None):
        calls.append(actor)
        if actor == "comments-primary":
            return [], ""
        return [{"text": "Muy buena receta", "uniqueId": "fan", "diggCount": 3}], ""

    monkeypatch.setattr(r, "_run_sync", fake_run)
    status, result = r.run_comments("7635981647359380758", 10)
    assert status == "ok"
    assert calls == ["comments-primary", "comments-secondary"]
    assert result["comments"][0]["texto"] == "Muy buena receta"
    assert result["comments_meta"]["source_used"] == "fallback"
    assert result["comments_meta"]["returned_count"] == 1
    assert result["comments_meta"]["source_used"] == "fallback"
    assert result["comments_meta"]["returned_count"] == 1


def test_comments_router_deduplicates_known_ids_and_keeps_unknown_ids(monkeypatch):
    import tiktok_router as r
    monkeypatch.setattr(r, "ACTOR_COMMENTS", "comments-primary")
    monkeypatch.setattr(r, "ACTOR_COMMENTS_FALLBACK", "")
    monkeypatch.setattr(r, "_run_sync", lambda *args, **kwargs: ([
        {"id": "c1", "text": "Mismo texto", "uniqueId": "fan1"},
        {"id": "c1", "text": "Duplicado", "uniqueId": "fan1"},
        {"text": "Mismo texto", "uniqueId": "fan2"},
        {"text": "Mismo texto", "uniqueId": "fan3"},
    ], ""))
    status, result = r.run_comments("7635981647359380758", 10)
    assert status == "ok"
    assert len(result["comments"]) == 3
    assert result["comments_meta"]["duplicate_count"] == 1
    assert result["comments_meta"]["unique_id_count"] == 1
    assert result["comments_meta"]["returned_count"] == 3
    assert result["comments_meta"]["field_coverage_pct"]["autor"] == 100.0


def test_comments_router_deduplicates_known_ids_and_keeps_unknown_ids(monkeypatch):
    import tiktok_router as r
    monkeypatch.setattr(r, "ACTOR_COMMENTS", "comments-primary")
    monkeypatch.setattr(r, "ACTOR_COMMENTS_FALLBACK", "")
    monkeypatch.setattr(r, "_run_sync", lambda *args, **kwargs: ([
        {"id": "c1", "text": "Mismo texto", "uniqueId": "fan1"},
        {"id": "c1", "text": "Duplicado", "uniqueId": "fan1"},
        {"text": "Mismo texto", "uniqueId": "fan2"},
        {"text": "Mismo texto", "uniqueId": "fan3"},
    ], ""))
    status, result = r.run_comments("7635981647359380758", 10)
    assert status == "ok"
    assert len(result["comments"]) == 3
    assert result["comments_meta"]["duplicate_count"] == 1
    assert result["comments_meta"]["unique_id_count"] == 1
    assert result["comments_meta"]["returned_count"] == 3
    assert result["comments_meta"]["field_coverage_pct"]["autor"] == 100.0


def test_mcp_private_tools_return_json_and_use_router(monkeypatch, tmp_path):
    import json
    import mcp_server
    import cache as cache_module

    monkeypatch.setattr(cache_module, "CACHE_SQLITE_PATH", tmp_path / "mcp-search.sqlite3")
    monkeypatch.setattr(cache_module, "_client", None)
    monkeypatch.setattr(cache_module, "_sync_client", None)
    monkeypatch.setattr(cache_module, "_sync_redis_tried", True)
    monkeypatch.setattr(cache_module, "_mem", {})
    async def no_redis():
        return None
    monkeypatch.setattr(cache_module, "_redis", no_redis)
    monkeypatch.setattr(mcp_server, "_free_mcp_search_enabled", lambda: True)
    mcp_server._MCP_CACHE.clear()
    monkeypatch.setattr(r, "run_search", lambda q, limit: ("ok", {
        "videos": [{"id": "10", "desc": q, "autor": "cocina_es", "likes": 10}],
        "free_miss": False
    }))
    result = json.loads(mcp_server.tiktok_search("paella", 3))
    assert result["videos"][0]["desc"] == "paella"
    assert result["cached"] is False
    mcp_server._MCP_CACHE.clear()


def test_mcp_private_profile_and_comments_tools_execute_queries(monkeypatch, tmp_path):
    import json
    import mcp_server
    import cache as cache_module

    monkeypatch.setattr(cache_module, "CACHE_SQLITE_PATH", tmp_path / "mcp-profile-comments.sqlite3")
    monkeypatch.setattr(cache_module, "_client", None)
    monkeypatch.setattr(cache_module, "_sync_client", None)
    monkeypatch.setattr(cache_module, "_sync_redis_tried", True)
    monkeypatch.setattr(cache_module, "_mem", {})
    async def no_redis():
        return None
    monkeypatch.setattr(cache_module, "_redis", no_redis)
    monkeypatch.setattr(mcp_server, "_free_mcp_search_enabled", lambda: True)
    mcp_server._MCP_CACHE.clear()
    monkeypatch.setattr(r, "run_profile", lambda user: ("ok", {
        "user": user, "bio": "Recetas", "followers": 10, "ultimos": [], "free_miss": False
    }))
    monkeypatch.setattr(r, "run_comments", lambda video_id, limit: ("ok", {
        "id": video_id, "comments": [{"autor": "fan", "texto": "hola", "likes": 1}], "free_miss": False
    }))
    profile = json.loads(mcp_server.tiktok_perfil_info("cocina_es"))
    comments = json.loads(mcp_server.tiktok_comments_info("7635981647359380758", 10))
    assert profile["user"] == "cocina_es"
    assert profile["bio"] == "Recetas"
    assert comments["comments"][0]["texto"] == "hola"
    assert profile["cached"] is False
    assert comments["cached"] is False
    mcp_server._MCP_CACHE.clear()


def test_mcp_public_profile_and_comments_give_executable_http_body(monkeypatch):
    import json
    import mcp_server
    monkeypatch.setattr(mcp_server, "_free_mcp_search_enabled", lambda: False)
    profile = json.loads(mcp_server.tiktok_perfil_info("cocina_es"))
    comments = json.loads(mcp_server.tiktok_comments_info("7635981647359380758", 12))
    assert profile["payment_required"] is True
    assert profile["price"] == "0.08 USDC"
    assert profile["body"] == {"user": "cocina_es"}
    assert comments["price"] == "0.05 USDC"
    assert comments["body"] == {"id": "7635981647359380758", "max": 12}


def test_failed_provider_cost_is_unknown_not_zero(tmp_path, monkeypatch):
    log = tmp_path / "cost.jsonl"
    monkeypatch.setattr(r, "COSTLOG_PATH", log)
    r.log_coste("apidojo~tiktok-scraper", "search", 0, 50000, False)
    record = json.loads(log.read_text(encoding="utf-8").strip())
    assert record["cost_est_usd"] is None
    assert record["cost_basis"] == "failed_run_cost_unknown"


def test_apidojo_profile_and_comments_payload_adapters():
    profile = r._payload_for_actor(
        "apidojo~tiktok-profile-scraper", "cocina_es", 10, kind="perfil",
        payload={"profiles": ["cocina_es"], "resultsPerPage": 10}
    )
    assert profile == {"usernames": ["cocina_es"], "maxItems": 10}
    comments = r._payload_for_actor(
        "apidojo~tiktok-comments-scraper", "https://www.tiktok.com/@x/video/123456789", 12,
        kind="comments",
        payload={"postURLs": ["https://www.tiktok.com/@x/video/123456789"], "commentsPerPost": 12}
    )
    assert comments == {
        "startUrls": ["https://www.tiktok.com/@x/video/123456789"],
        "maxItems": 12,
        "includeReplies": False,
    }


def test_comments_normalizer_supports_apidojo_nested_user():
    monkeypatch_data = [{
        "text": "Muy buena receta",
        "likeCount": 9,
        "user": {"username": "fan_es", "displayName": "Fan ES"},
    }]
    # Reutiliza el actor de comentarios sin salida externa.
    old_actor = r.ACTOR_COMMENTS
    old_fallback = r.ACTOR_COMMENTS_FALLBACK
    try:
        r.ACTOR_COMMENTS = "test-comments"
        r.ACTOR_COMMENTS_FALLBACK = ""
        original_run = r._run_sync
        r._run_sync = lambda actor, payload, kind="search", timeout_s=None: (monkeypatch_data, "")
        status, result = r.run_comments("7635981647359380758", 10)
        assert status == "ok"
        comment = result["comments"][0]
        assert comment["autor"] == "fan_es"
        assert comment["autor_usuario"] == "fan_es"
        assert comment["autor_nombre"] == "Fan ES"
        assert comment["texto"] == "Muy buena receta"
        assert comment["likes"] == 9
        assert comment["respuestas"] is None
    finally:
        r.ACTOR_COMMENTS = old_actor
        r.ACTOR_COMMENTS_FALLBACK = old_fallback
        r._run_sync = original_run


def test_profile_fallback_receives_apidojo_input_schema(monkeypatch):
    monkeypatch.setattr(r, "ACTOR_PROFILE", "profile-primary")
    monkeypatch.setattr(r, "ACTOR_PROFILE_FALLBACK", "apidojo~tiktok-profile-scraper")
    calls = []

    def fake_run(actor, payload, kind="search", timeout_s=None):
        calls.append((actor, payload, kind))
        if actor == "profile-primary":
            return [], ""
        return [{
            "id": "123", "text": "video reciente",
            "authorMeta": {"uniqueId": "cocina_es", "signature": "Recetas", "fans": 321},
        }], ""

    monkeypatch.setattr(r, "_run_sync", fake_run)
    status, result = r.run_profile("cocina_es")
    assert status == "ok"
    assert calls[0][1]["profiles"] == ["cocina_es"]
    assert calls[1][0] == "apidojo~tiktok-profile-scraper"
    assert calls[1][1] == {"usernames": ["cocina_es"], "maxItems": 10}
    assert calls[1][2] == "perfil"
    assert result["followers"] == 321


def test_comments_fallback_receives_apidojo_input_schema(monkeypatch):
    monkeypatch.setattr(r, "ACTOR_COMMENTS", "comments-primary")
    monkeypatch.setattr(r, "ACTOR_COMMENTS_FALLBACK", "apidojo~tiktok-comments-scraper")
    calls = []

    def fake_run(actor, payload, kind="search", timeout_s=None):
        calls.append((actor, payload, kind))
        if actor == "comments-primary":
            return [], ""
        return [{
            "text": "Comentario público",
            "likeCount": 4,
            "user": {"username": "fan_es"},
        }], ""

    monkeypatch.setattr(r, "_run_sync", fake_run)
    status, result = r.run_comments("7635981647359380758", 12)
    assert status == "ok"
    assert calls[1][0] == "apidojo~tiktok-comments-scraper"
    assert calls[1][1] == {
        "startUrls": ["https://www.tiktok.com/@/video/7635981647359380758"],
        "maxItems": 12,
        "includeReplies": False,
    }
    assert result["comments"][0]["autor"] == "fan_es"


def test_health_reports_sanitized_scraper_status(monkeypatch):
    import tiktok_router as router
    monkeypatch.setattr(router, "_token", lambda: "configured-token-do-not-serialize")
    monkeypatch.setattr(router, "actor_health", lambda: {
        "top": "secret-primary-actor", "fallback": "secret-fallback-actor",
        "top_fails": 2, "fallback_fails": 1, "quality_fallback_fails": 3,
        "prefer_fallback": True, "budget_s": 48, "per_actor_timeout_s": 18,
    })
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["scraper"]["apify_configured"] is True
    assert body["scraper"]["primary_failures"] == 2
    assert body["scraper"]["profile_fallback_configured"] is True
    assert body["scraper"]["comments_fallback_configured"] is True
    serialized = response.text
    assert "configured-token-do-not-serialize" not in serialized
    assert "secret-primary-actor" not in serialized
    assert "secret-fallback-actor" not in serialized


def test_sqlite_cache_shared_between_rest_async_and_mcp_sync(tmp_path, monkeypatch):
    import asyncio
    import cache as cache_module

    db_path = tmp_path / "shared-cache.sqlite3"
    monkeypatch.setattr(cache_module, "CACHE_SQLITE_PATH", db_path)
    monkeypatch.setattr(cache_module, "CACHE_REQUIRE_REDIS", False)
    monkeypatch.setattr(cache_module, "_client", None)
    monkeypatch.setattr(cache_module, "_sync_client", None)
    monkeypatch.setattr(cache_module, "_sync_redis_tried", True)

    async def no_redis():
        return None

    monkeypatch.setattr(cache_module, "_redis", no_redis)

    asyncio.run(cache_module.put("tiktok:v2:search:ES:paella:2", {
        "q": "paella", "videos": [{"id": "1", "cover": "https://example.test/1.jpg"}],
        "free_miss": False,
    }, ttl=120))
    through_mcp = cache_module.get_sync("tiktok:v2:search:ES:paella:2")
    assert through_mcp["videos"][0]["cover"] == "https://example.test/1.jpg"

    cache_module.put_sync("tiktok:v2:comments:123456789:10", {
        "id": "123456789", "comments": [{"texto": "hola"}], "free_miss": False,
    }, ttl=120)
    through_rest = asyncio.run(cache_module.get("tiktok:v2:comments:123456789:10"))
    assert through_rest["comments"][0]["texto"] == "hola"
    assert db_path.exists()


def test_sqlite_cache_expires_entries_and_prunes_expired(tmp_path, monkeypatch):
    import cache as cache_module

    now = [1000.0]
    monkeypatch.setattr(cache_module, "CACHE_SQLITE_PATH", tmp_path / "expiry.sqlite3")
    monkeypatch.setattr(cache_module.time, "time", lambda: now[0])
    cache_module._sqlite_put("expired", {"v": 1}, ttl=1)
    now[0] += 2
    assert cache_module._sqlite_get("expired") is None
    with cache_module._sqlite_connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM cache_entries WHERE cache_key='expired'").fetchone()[0] == 0


def test_health_reports_sqlite_as_shared_cache_when_redis_is_unavailable(monkeypatch, tmp_path):
    import cache as cache_module

    monkeypatch.setattr(cache_module, "CACHE_SQLITE_PATH", tmp_path / "health-cache.sqlite3")
    monkeypatch.setattr(cache_module, "CACHE_REQUIRE_REDIS", False)
    async def no_redis():
        return None
    monkeypatch.setattr(cache_module, "_redis", no_redis)
    monkeypatch.setattr(cache_module, "_client", None)

    import asyncio
    status = asyncio.run(cache_module.backend_status())
    assert status["backend"] == "sqlite"
    assert status["shared_between_workers"] is True


def test_provider_cost_estimates_use_public_ppr_and_failures_remain_unknown(tmp_path, monkeypatch):
    log = tmp_path / "cost.jsonl"
    monkeypatch.setattr(r, "COSTLOG_PATH", log)
    token = r.set_cost_request_id("payment-fingerprint-test")
    try:
        r.log_coste("apidojo~tiktok-scraper", "search", 0, 50000, False)
        r.log_coste("apidojo~tiktok-scraper", "search", 10, 4000, True)
    finally:
        r.reset_cost_request_id(token)
    r.log_coste("unknown-actor", "search", 10, 1000, True)
    rows = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["cost_est_usd"] is None
    assert rows[0]["cost_basis"] == "failed_run_cost_unknown"
    assert rows[1]["cost_est_usd"] == 0.003
    assert rows[1]["cost_basis"] == "published_starting_price_estimate"
    assert rows[1]["request_id"] == "payment-fingerprint-test"
    assert rows[2]["cost_est_usd"] is None
    assert rows[2]["cost_basis"] == "provider_cost_not_verified"


def test_empty_provider_success_is_not_assumed_to_be_free(tmp_path, monkeypatch):
    log = tmp_path / "empty-cost.jsonl"
    monkeypatch.setattr(r, "COSTLOG_PATH", log)
    r.log_coste("clockworks~tiktok-scraper", "search", 0, 3000, True)
    record = json.loads(log.read_text(encoding="utf-8").strip())
    assert record["cost_est_usd"] is None
    assert record["cost_basis"] == "empty_run_cost_unknown"


def test_normalize_preserves_fractional_duration_and_string_boolean():
    out = r.normalize_dataset([{
        "id": "duration-test",
        "text": "Skincare",
        "videoMeta": {"duration": 7.638, "coverUrl": "https://example.test/c.jpg"},
        "webVideoUrl": "https://www.tiktok.com/@user/video/123456789",
        "isAd": "false",
        "createTimeISO": "2026-10-01T00:00:00Z",
        "authorMeta": {"uniqueId": "user"},
    }])
    assert out["videos"][0]["duration"] == 7.638
    assert out["videos"][0]["is_ad"] is False


def test_search_meta_reports_quality_without_provider_ids(monkeypatch):
    monkeypatch.setattr(r, "ACTOR_SEARCH", "primary")
    monkeypatch.setattr(r, "ACTOR_FALLBACK", "")
    monkeypatch.setattr(r, "ACTOR_SEARCH_QUALITY_FALLBACK", "")
    monkeypatch.setattr(r, "SEARCH_BUDGET_S", 48)
    monkeypatch.setattr(r, "SYNC_TIMEOUT_S", 5)
    monkeypatch.setattr(r, "_run_sync", lambda actor, payload, kind="search", timeout_s=None: ([
        {"id": "1", "text": "Receta de paella", "authorMeta": {"uniqueId": "cocina"},
         "likes": 3, "hashtags": ["paella"], "videoMeta": {"coverUrl": "https://example.test/cover.jpg"},
         "webVideoUrl": "https://www.tiktok.com/@cocina/video/123456789",
         "createTimeISO": "2026-10-01T00:00:00Z"}
    ], ""))
    status, result = r.run_search("receta paella", 1)
    assert status == "ok"
    assert result["search_meta"]["sources_consulted"] == 1
    assert result["search_meta"]["fallback_used"] is False
    assert result["search_meta"]["cover_coverage"] == 1.0
    assert result["search_meta"]["url_coverage"] == 1.0
    assert "primary" not in json.dumps(result)
    assert result["videos"][0]["relevancia"] == 1.0


def test_paid_search_rejects_more_than_twenty_results_before_payment(tmp_path, monkeypatch):
    import server_v1
    monkeypatch.setattr(server_v1, "METRICS_PATH", tmp_path / "metrics.jsonl")
    response = client.post(
        "/v1/tiktok/search",
        headers={"PAYMENT-SIGNATURE": "invalid-placeholder"},
        json={"q": "paella", "max": 21},
    )
    assert response.status_code == 400
    assert "1 y 20" in response.json()["error"]


def test_sales_ledger_can_correlate_sale_and_costs(tmp_path, monkeypatch):
    import paywall as payment_module
    sales = tmp_path / "sales.jsonl"
    seen = tmp_path / "seen.json"
    monkeypatch.setattr(payment_module, "SALES_PATH", sales)
    monkeypatch.setattr(payment_module, "SEEN_PATH", seen)
    assert payment_module.log_venta(
        "0x0000000000000000000000000000000000000001",
        "0xtesttransaction", "search", request_id="fingerprint123",
        cache_hit=True, result_count=7,
    )
    row = json.loads(sales.read_text(encoding="utf-8").strip())
    assert row["request_id"] == "fingerprint123"
    assert row["cache_hit"] is True
    assert row["result_count"] == 7


def test_api_metrics_count_payment_challenges_without_query_or_identity(tmp_path, monkeypatch):
    import json
    import server_v1
    monkeypatch.setattr(server_v1, "METRICS_PATH", tmp_path / "metrics.jsonl")
    response = client.post("/v1/tiktok/search", json={"q": "paella confidencial"})
    assert response.status_code == 402
    row = json.loads((tmp_path / "metrics.jsonl").read_text(encoding="utf-8").strip())
    assert row["event"] == "payment_challenge"
    assert row["endpoint"] == "/v1/tiktok/search"
    assert "paella" not in json.dumps(row)
    assert "payer" not in row and "ip" not in row and "signature" not in row


def test_api_metrics_record_settlement_and_free_miss_categories_without_identity(tmp_path, monkeypatch):
    import json
    import server_v1
    monkeypatch.setattr(server_v1, "METRICS_PATH", tmp_path / "payment-outcomes.jsonl")
    server_v1._record_api_metric("payment_completed", "/v1/tiktok/search", 200, 12)
    server_v1._record_api_metric("free_miss", "/v1/tiktok/comments", 200, 0)
    rows = [
        json.loads(line)
        for line in (tmp_path / "payment-outcomes.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert [row["event"] for row in rows] == ["payment_completed", "free_miss"]
    assert all("query" not in row and "payer" not in row and "signature" not in row for row in rows)
