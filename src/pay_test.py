"""Pago test mainnet $0.08 con stack oficial x402 (task 6.2). Lee PAYER_KEY.txt,
firma via ExactEvmScheme, paga via wrapHttpxWithPayment. Nunca imprime la key."""
import asyncio
import json
from pathlib import Path

import httpx
from eth_account import Account

from x402.client import x402Client
from x402.client_base import SchemeRegistration, x402ClientConfig
from x402.http.clients.httpx import wrapHttpxWithPayment
from x402.mechanisms.evm.exact.client import ExactEvmScheme

BASE_DIR = Path(__file__).resolve().parent.parent
ENDPOINT = "https://veredicto.dpdns.org/v1/tiktok/search"


async def main():
    lines = [l.strip() for l in (BASE_DIR / "PAYER_KEY.txt").read_text(encoding="utf-8").splitlines()
             if l.strip()]
    raw = next(l for l in lines if not l.startswith("0x") and len(l) == 64)
    acct = Account.from_key("0x" + raw)
    reg = SchemeRegistration(network="eip155:8453", client=ExactEvmScheme(acct), x402_version=2)
    client = x402Client.from_config(x402ClientConfig(schemes=[reg]))
    wrapped = wrapHttpxWithPayment(client, timeout=170.0)
    async with wrapped:
        r = await wrapped.post(ENDPOINT, json={"q": "paella", "max": 2})
        print("STATUS:", r.status_code)
        print("PAYMENT-RESPONSE:", (r.headers.get("payment-response") or "")[:200])
        body = r.json()
        vids = body.get("videos", [])
        print("VIDEOS:", len(vids), "first_id:", (vids[0].get("id") if vids else None),
              "cached:", body.get("cached"), "free_miss:", body.get("free_miss"))


asyncio.run(main())
