import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fastapi.testclient import TestClient

import server_v1 as s
import tiktok_router as r
import paywall as p

client = TestClient(s.app)


def setup_function(_):
    s._RATE_IP.clear()
    s._RATE_WALLET.clear()


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
