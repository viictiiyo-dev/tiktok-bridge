#!/usr/bin/env python3
"""Paywall x402 Base/CDP para TIKTOK BRIDGE (task 2).
Migrado del patrón probado de AGENTE COMPARADOR server.py.
Wallet SEPARADA por env X402_PAY_TO_TIKTOK. Solo Base mainnet.
Precios: search 80000 (0.08), perfil 80000, comments 50000 (0.05).
"""
import base64
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

for _env in (Path(__file__).resolve().parent.parent / ".env", Path(__file__).resolve().parent / ".env"):
    try:
        for _line in _env.read_text(encoding="utf-8").splitlines():
            _line = _line.strip()
            if not _line or _line.startswith("#") or "=" not in _line:
                continue
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())
    except OSError:
        pass

X402_SCHEME = "exact"
BASE_NETWORK = "eip155:8453"
BASE_ASSET = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
BASE_PAY_TO = os.environ.get("X402_PAY_TO_TIKTOK", "").strip()
X402_TIMEOUT_S = 60
CDP_FACILITATOR_URL = "https://api.cdp.coinbase.com/platform/v2/x402"

PRICE = {"search": "80000", "perfil": "80000", "comments": "50000"}
PRICE_LABEL = {"search": "0.08 USDC", "perfil": "0.08 USDC", "comments": "0.05 USDC"}

SALES_PATH = Path(os.environ.get("VENTAS_PATH", str(Path(__file__).resolve().parent / "ventas_tiktok.jsonl")))
SEEN_PATH = Path(os.environ.get("SEEN_PATH", str(Path(__file__).resolve().parent / "seen_tx.json")))


def _load_dotenv():
    # Sin dependencias: parse KEY=VALUE (sin export, sin comillas complejas).
    for cand in (Path(__file__).resolve().parent.parent / ".env",
                 Path(__file__).resolve().parent / ".env"):
        try:
            for line in cand.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
        except OSError:
            pass


_load_dotenv()


def _cdp_key():
    kid = os.environ.get("CDP_API_KEY_ID", "").strip()
    sec = os.environ.get("CDP_API_KEY_SECRET", "").strip()
    if kid and sec:
        return kid, sec
    for cand in (Path(__file__).resolve().parent.parent / "cdp_tiktok.txt",
                 Path(__file__).resolve().parent.parent.parent / "AGENTE COMPARADOR" / "cdp.txt"):
        try:
            lines = [l.strip() for l in cand.read_text(encoding="utf-8").splitlines() if l.strip()]
            if len(lines) >= 2:
                return lines[0], lines[1]
        except OSError:
            pass
    return "", ""


def methods(kind: str = "search") -> list:
    return [{"scheme": X402_SCHEME, "network": BASE_NETWORK, "amount": PRICE[kind],
             "asset": BASE_ASSET, "payTo": BASE_PAY_TO,
             "maxTimeoutSeconds": X402_TIMEOUT_S, "extra": {"name": "USD Coin", "version": "2"}}]


def challenge(url: str, kind: str, example: dict) -> dict:
    # El validador CDP exige info.input.method; el helper no lo infiere sin route key,
    # así que se inyecta a mano tras generar la extensión oficial.
    inputs = {"search": ({"q": "paella", "max": 20},
                         {"properties": {"q": {"type": "string"}, "max": {"type": "integer"}},
                          "required": ["q"]}),
              "perfil": ({"user": "cocina_es"},
                         {"properties": {"user": {"type": "string"}}, "required": ["user"]}),
              "comments": ({"id": "7635981647359380758", "max": 50},
                           {"properties": {"id": {"type": "string"}, "max": {"type": "integer"}},
                            "required": ["id"]})}
    body_ex, schema = inputs.get(kind, ({}, {}))
    ch = {
        "x402Version": 2, "error": "Payment required",
        "resource": {"url": url,
                     "description": f"TikTok {kind} para agentes. SOLO PUBLICO. Free-miss si 0 resultados.",
                     "mimeType": "application/json", "serviceName": "TikTok Bridge",
                     "tags": ["tiktok", "search", "agents", "x402"]},
        "accepts": methods(kind), "price": PRICE_LABEL[kind],
        "output": {"example": example},
        "how": "Repite este POST con PAYMENT-SIGNATURE (PaymentPayload x402 v2 base64).",
    }
    try:
        from x402.extensions.bazaar import OutputConfig, declare_discovery_extension
        ch["extensions"] = declare_discovery_extension(
            input=body_ex, input_schema=schema, body_type="json",
            output=OutputConfig(example=example))
        ch["extensions"]["bazaar"]["info"]["input"]["method"] = "POST"
    except Exception:
        pass
    return ch


def structural_ok(payload_b64: str, kind: str) -> tuple:
    try:
        p = json.loads(base64.b64decode(payload_b64).decode("utf-8"))
    except Exception:
        return False, "payload no es JSON base64 valido"
    pay = p.get("payload", p)
    acc = p.get("accepted", {})
    sig = pay.get("signature", "")
    sig_ok = isinstance(sig, str) and ((len(sig) == 132 and sig.startswith("0x")) or (87 <= len(sig) <= 88))
    if not sig_ok:
        return False, "firma ausente o malformada"
    try:
        pay_int = int(str(acc.get("maxAmountRequired", acc.get("amount", pay.get("amount", "0")))) or 0)
    except (TypeError, ValueError):
        return False, "importe no numerico"
    if pay_int < int(PRICE[kind]):
        return False, f"importe menor que {PRICE[kind]}"
    pay_to = str(acc.get("payTo", pay.get("payTo", pay.get("to", ""))))
    if not pay_to or (BASE_PAY_TO and pay_to.lower() != BASE_PAY_TO.lower()):
        return False, "destino no aceptado en este tier"
    if pay.get("network", acc.get("network", "")) not in ("", BASE_NETWORK):
        return False, "red no aceptada (solo Base mainnet)"
    return True, "ok-estructural"


LAST_EXT: dict = {}


def bazaar_status() -> dict:
    """Decodifica EXTENSION-RESPONSES del último settle: success/processing/rejected + motivo."""
    raw = LAST_EXT.get("/settle", "")
    if not raw:
        return {"status": "sin-datos"}
    try:
        data = json.loads(base64.b64decode(raw).decode("utf-8"))
        bz = (data.get("bazaar") or {})
        return {"status": bz.get("status", "?"),
                "reason": str(bz.get("rejectedReason", ""))[:300]}
    except Exception as e:
        return {"status": "ilegible", "reason": type(e).__name__}


def facilitator_call_cdp(path: str, payload: dict, requirements: dict) -> dict:
    # gotcha Context7: create_facilitator_config() lee env o acepta (id, secret); headers por path.
    # El header EXTENSION-RESPONSES (bazaar: success/processing/rejected) se guarda en LAST_EXT.
    from cdp.x402 import create_facilitator_config
    kid, sec = _cdp_key()
    if not (kid and sec):
        raise RuntimeError("sin clave CDP")
    cfg = create_facilitator_config(kid, sec) if kid != "env" else create_facilitator_config()
    headers = dict(cfg["create_headers"]()[path.strip("/")])
    headers.update({"Content-Type": "application/json", "Accept": "application/json"})
    body = json.dumps({"x402Version": 2, "paymentPayload": payload,
                       "paymentRequirements": requirements}).encode()
    req = urllib.request.Request(CDP_FACILITATOR_URL + path, data=body, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            data = json.load(r)
            try:
                LAST_EXT[path] = r.headers.get("EXTENSION-RESPONSES", "")
            except Exception:
                pass
            return data
    except urllib.error.HTTPError as e:
        if e.code in (400, 422):
            try:
                detail = json.load(e)
            except Exception:
                detail = {}
            return {"isValid": False, "success": False,
                    "invalidReason": str(detail.get("invalidReason", detail.get("message", detail)))[:200] or f"cdp-{e.code}"}
        raise


def _seen() -> set:
    try:
        return set(json.loads(SEEN_PATH.read_text(encoding="utf-8")))
    except OSError:
        return set()


def _mark_seen(tx: str):
    try:
        s = _seen()
        s.add(tx)
        SEEN_PATH.write_text(json.dumps(sorted(s)[-5000:]), encoding="utf-8")
    except OSError:
        pass


def log_venta(payer: str, tx: str, kind: str):
    # idempotency: mismo tx no cuenta dos veces.
    if tx and tx in _seen():
        return False
    if tx:
        _mark_seen(tx)
    try:
        with open(SALES_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": int(time.time()), "payer": payer, "tx": tx,
                                "amount": PRICE[kind], "kind": kind, "network": BASE_NETWORK,
                                "settled_by_facilitator": True,
                                "settlement_source": "x402_facilitator"}) + "\n")
    except OSError:
        pass
    return True
