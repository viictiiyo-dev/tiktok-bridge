/**
 * Cliente de ejemplo para TikTok Bridge con pago x402 automático.
 *
 * Seguridad: este script NO hará ninguna solicitud hasta que confirmes
 * explícitamente TIKTOK_BRIDGE_ALLOW_LIVE_PAYMENT=YES. La ejecución puede pagar 0.08 USDC.
 *
 * Requisitos: Node.js 20+, @x402/fetch, @x402/evm, viem.
 * Instala: npm install @x402/fetch @x402/evm viem
 *
 * Variables de entorno:
 *   EVM_PRIVATE_KEY=0x...               (wallet con USDC en Base)
 *   TIKTOK_BRIDGE_ALLOW_LIVE_PAYMENT=YES (consentimiento explícito)
 *
 * Ejemplo: node examples/tiktok_bridge_x402_client.mjs "receta paella" 10
 */
import { x402Client, wrapFetchWithPayment } from "@x402/fetch";
import { registerExactEvmScheme } from "@x402/evm/exact/client";
import { privateKeyToAccount } from "viem/accounts";

const ENDPOINT = "https://veredicto.dpdns.org/v1/tiktok/search";

async function main() {
  if (process.env.TIKTOK_BRIDGE_ALLOW_LIVE_PAYMENT !== "YES") {
    throw new Error(
      "Pago bloqueado. Define TIKTOK_BRIDGE_ALLOW_LIVE_PAYMENT=YES tras revisar el coste de 0.08 USDC por consulta."
    );
  }

  const privateKey = process.env.EVM_PRIVATE_KEY;
  if (!privateKey || !/^0x[0-9a-fA-F]{64}$/.test(privateKey)) {
    throw new Error("Falta EVM_PRIVATE_KEY válida en el entorno; no la incluyas en el código ni en Git.");
  }

  const q = String(process.argv[2] ?? "").trim();
  const max = Number(process.argv[3] ?? 10);
  if (!q) throw new Error('Uso: node examples/tiktok_bridge_x402_client.mjs "consulta" [max]');
  if (!Number.isInteger(max) || max < 1 || max > 20) {
    throw new Error("max debe ser un entero de 1 a 20; el precio actual es 0.08 USDC.");
  }

  const paymentClient = new x402Client();
  const signer = privateKeyToAccount(privateKey);
  registerExactEvmScheme(paymentClient, { signer });
  const fetchWithPayment = wrapFetchWithPayment(fetch, paymentClient);

  // No imprime la clave, firma ni contenido del pago.
  const response = await fetchWithPayment(ENDPOINT, {
    method: "POST",
    headers: { "Content-Type": "application/json", "Accept": "application/json" },
    body: JSON.stringify({ q, max }),
  });

  const body = await response.json().catch(() => ({ error: "La respuesta no contiene JSON válido." }));
  if (!response.ok) {
    throw new Error("TikTok Bridge respondió HTTP " + response.status + ": " + JSON.stringify(body));
  }
  console.log(JSON.stringify(body, null, 2));
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : "Error desconocido");
  process.exitCode = 1;
});
