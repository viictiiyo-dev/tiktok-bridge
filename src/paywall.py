#!/usr/bin/env python3
"""Paywall x402 Base/CDP para TIKTOK BRIDGE (task 2).
Migrado del patrón probado de AGENTE COMPARADOR server.py.
Wallet SEPARADA por env X402_PAY_TO_TIKTOK. Solo Base mainnet.
Precios: search 80000 (0.08), perfil 80000, comments 50000 (0.05).
"""
import base64
import hashlib
import json
import logging
import os
import sqlite3
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
REQUESTS_PATH = Path(os.environ.get(
    "PAYMENT_REQUESTS_PATH", str(Path(__file__).resolve().parent / "payment_requests.sqlite3")
))


def _request_db():
    """SQLite persistente para impedir liquidaciones duplicadas incluso tras reinicios."""
    REQUESTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(REQUESTS_PATH), timeout=10, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=10000")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS payment_requests (
            fingerprint TEXT PRIMARY KEY,
            state TEXT NOT NULL,
            updated_at INTEGER NOT NULL,
            response_body TEXT,
            payment_response TEXT,
            status_code INTEGER NOT NULL DEFAULT 200,
            error TEXT
        )"""
    )
    return conn


def _request_record(row):
    if row is None:
        return None
    try:
        body = json.loads(row["response_body"]) if row["response_body"] else None
    except json.JSONDecodeError:
        body = None
    return {
        "state": row["state"],
        "updated_at": row["updated_at"],
        "response_body": body,
        "payment_response": row["payment_response"] or "",
        "status_code": int(row["status_code"] or 200),
        "error": row["error"] or "",
    }


def begin_payment_request(signature: str):
    """Reserva una firma verificada de forma atomica; un duplicado nunca empieza otro settle."""
    fingerprint = hashlib.sha256(signature.encode("utf-8")).hexdigest()
    now = int(time.time())
    conn = _request_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT * FROM payment_requests WHERE fingerprint=?", (fingerprint,)
        ).fetchone()
        if row is not None:
            # Una caida durante la busqueda (antes de marcar 'settling') puede recuperarse
            # tras 3 minutos. Nunca recuperamos automaticamente una liquidacion iniciada.
            if row["state"] == "processing" and now - int(row["updated_at"]) > 180:
                conn.execute(
                    "UPDATE payment_requests SET updated_at=? WHERE fingerprint=?",
                    (now, fingerprint),
                )
                conn.commit()
                return fingerprint, "new", None
            record = _request_record(row)
            conn.commit()
            return fingerprint, record["state"], record
        conn.execute(
            "INSERT INTO payment_requests (fingerprint,state,updated_at) VALUES (?,?,?)",
            (fingerprint, "processing", now),
        )
        conn.commit()
        return fingerprint, "new", None
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def mark_payment_request_state(
    fingerprint: str, state: str, response_body=None, payment_response=None,
    status_code=None, error=None
):
    """Persistir la transicion antes/despu?s de interactuar con el facilitador."""
    conn = _request_db()
    try:
        row = conn.execute(
            "SELECT * FROM payment_requests WHERE fingerprint=?", (fingerprint,)
        ).fetchone()
        if row is None:
            raise RuntimeError("firma de pago no reservada")
        body_json = row["response_body"]
        if response_body is not None:
            body_json = json.dumps(response_body, ensure_ascii=False, separators=(",", ":"))
        presp = row["payment_response"] or ""
        if payment_response is not None:
            presp = payment_response
        code = int(row["status_code"] or 200) if status_code is None else int(status_code)
        err = row["error"] or "" if error is None else str(error)[:300]
        conn.execute(
            """UPDATE payment_requests SET state=?,updated_at=?,response_body=?,
               payment_response=?,status_code=?,error=? WHERE fingerprint=?""",
            (state, int(time.time()), body_json, presp, code, err, fingerprint),
        )
    finally:
        conn.close()


def complete_payment_request(fingerprint: str, response_body: dict, payment_response: str = ""):
    mark_payment_request_state(
        fingerprint, "completed", response_body=response_body,
        payment_response=payment_response, status_code=200, error=""
    )


def fail_payment_request(fingerprint: str, response_body: dict, status_code: int = 502):
    mark_payment_request_state(
        fingerprint, "failed", response_body=response_body,
        payment_response="", status_code=status_code
    )


def release_payment_request(fingerprint: str):
    """Liberar reservas solo si aun no se ha empezado /settle."""
    conn = _request_db()
    try:
        conn.execute(
            "DELETE FROM payment_requests WHERE fingerprint=? AND state='processing'",
            (fingerprint,),
        )
    finally:
        conn.close()


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
                         {"properties": {"q": {"type": "string"}, "max": {"type": "integer", "minimum": 1, "maximum": 20}},
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
    """Comprobaci?n defensiva de forma; la validez criptografica la confirma CDP."""
    try:
        p = json.loads(base64.b64decode(payload_b64, validate=True).decode("utf-8"))
    except Exception:
        return False, "payload no es JSON base64 valido"
    if not isinstance(p, dict):
        return False, "payload debe ser un objeto JSON"
    pay = p.get("payload", p)
    if not isinstance(pay, dict):
        return False, "payload interno malformado"
    acc = p.get("accepted", {})
    if not isinstance(acc, dict):
        return False, "accepted malformado"
    sig = pay.get("signature", "")
    sig_ok = isinstance(sig, str) and (
        (len(sig) == 132 and sig.startswith("0x")) or 87 <= len(sig) <= 88
    )
    if not sig_ok:
        return False, "firma ausente o malformada"
    try:
        amount_value = acc.get("maxAmountRequired", acc.get("amount", pay.get("amount", "0")))
        pay_int = int(str(amount_value or 0))
    except (TypeError, ValueError):
        return False, "importe no numerico"
    if pay_int < int(PRICE[kind]):
        return False, f"importe menor que {PRICE[kind]}"
    pay_to = acc.get("payTo", pay.get("payTo", pay.get("to", "")))
    if not isinstance(pay_to, str) or not pay_to or (
        BASE_PAY_TO and pay_to.lower() != BASE_PAY_TO.lower()
    ):
        return False, "destino no aceptado en este tier"
    network = pay.get("network", acc.get("network", ""))
    if not isinstance(network, str) or network not in ("", BASE_NETWORK):
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
        if not SEEN_PATH.exists():
            return set()
        parsed = json.loads(SEEN_PATH.read_text(encoding="utf-8"))
        if not isinstance(parsed, list):
            raise ValueError("seen_tx.json debe contener una lista")
        return set(str(tx) for tx in parsed)
    except FileNotFoundError:
        return set()
    except (json.JSONDecodeError, ValueError) as exc:
        # Conservar el archivo da?ado para diagn?stico y reconstrucci?n, sin tumbar
        # una petici?n pagada. La deduplicaci?n principal es payment_requests.sqlite3.
        corrupt = SEEN_PATH.with_name(SEEN_PATH.name + f".corrupt-{int(time.time())}")
        try:
            SEEN_PATH.replace(corrupt)
        except OSError:
            logging.exception("No se pudo aislar el ledger de transacciones corrupto")
        logging.error("Ledger seen_tx corrupto; aislado si fue posible (%s)", type(exc).__name__)
        return set()
    except OSError:
        logging.exception("No se pudo leer seen_tx; la deduplicaci?n sigue protegida por SQLite")
        return set()


def _mark_seen(tx: str):
    s = _seen()
    s.add(tx)
    tmp = SEEN_PATH.with_name(SEEN_PATH.name + ".tmp")
    tmp.write_text(json.dumps(sorted(s)), encoding="utf-8")
    tmp.replace(SEEN_PATH)


def log_venta(
    payer: str, tx: str, kind: str, request_id: str = "",
    cache_hit=None, result_count=None
):
    # La firma x402 queda registrada en SQLite antes del settle; el ledger de ventas
    # correlaciona costes mediante un hash y no persiste consultas ni payloads privados.
    if tx and tx in _seen():
        return False
    record = {"ts": int(time.time()), "payer": payer, "tx": tx,
              "amount": PRICE[kind], "kind": kind, "network": BASE_NETWORK,
              "settled_by_facilitator": True, "settlement_source": "x402_facilitator"}
    if request_id:
        record["request_id"] = str(request_id)[:100]
    if cache_hit is not None:
        record["cache_hit"] = bool(cache_hit)
    if result_count is not None:
        record["result_count"] = max(0, int(result_count))
    try:
        SALES_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(SALES_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except OSError:
        logging.exception("Pago liquidado pero no se pudo escribir ventas_tiktok.jsonl")
        return False
    if tx:
        try:
            _mark_seen(tx)
        except OSError:
            logging.exception("Pago registrado; no se pudo actualizar seen_tx.json")
    return True
