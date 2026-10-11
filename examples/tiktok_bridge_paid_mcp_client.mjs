/**
 * Cliente MCP pagado mediante Coinbase x402 Bazaar.
 *
 * No está conectado a TikTok Bridge directamente como MCP servidor:
 * usa el proxy MCP x402 para descubrir/invocar un recurso REST de pago.
 * Requiere que TikTok Bridge sea discoverable/listado en Bazaar y que el
 * toolName usado sea el publicado por search_resources.
 *
 * No envía peticiones pagadas salvo consentimiento explícito:
 *   TIKTOK_BRIDGE_ALLOW_LIVE_PAYMENT=YES
 *   EVM_PRIVATE_KEY=0x...  (no guardar en el repo)
 *
 * npm install @modelcontextprotocol/sdk @x402/mcp @x402/fetch @x402/evm viem
 *
 * node examples/tiktok_bridge_paid_mcp_client.mjs "TikTok Bridge" "<toolName-Bazaar>" '{"q":"paella","max":10}'
 */
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StreamableHTTPClientTransport } from "@modelcontextprotocol/sdk/client/streamableHttp.js";
import { createX402MCPClient } from "@x402/mcp";
import { x402Client } from "@x402/fetch";
import { registerExactEvmScheme } from "@x402/evm/exact/client";
import { privateKeyToAccount } from "viem/accounts";

const BAZAAR_MCP =
  "https://api.cdp.coinbase.com/platform/v2/x402/discovery/mcp";

async function main() {
  if (process.env.TIKTOK_BRIDGE_ALLOW_LIVE_PAYMENT !== "YES") {
    throw new Error(
      "Pago bloqueado: revisa el precio antes de poner TIKTOK_BRIDGE_ALLOW_LIVE_PAYMENT=YES."
    );
  }
  const privateKey = process.env.EVM_PRIVATE_KEY;
  if (!privateKey || !/^0x[0-9a-fA-F]{64}$/.test(privateKey)) {
    throw new Error("Falta EVM_PRIVATE_KEY válida en el entorno; no la guardes en el repositorio.");
  }

  const searchQuery = String(process.argv[2] ?? "TikTok Bridge");
  const toolName = String(process.argv[3] ?? "").trim();
  const argsText = String(process.argv[4] ?? '{"q":"paella","max":10}');
  if (!toolName) {
    throw new Error(
      'Falta toolName de Bazaar. Busca primero en Bazaar con "TikTok Bridge" y vuelve a ejecutar con el toolName listado.'
    );
  }
  let toolArgs;
  try {
    toolArgs = JSON.parse(argsText);
  } catch {
    throw new Error("El cuarto argumento debe ser un objeto JSON válido.");
  }
  if (!toolArgs || typeof toolArgs !== "object" || Array.isArray(toolArgs)) {
    throw new Error("Los argumentos del recurso deben ser un objeto JSON.");
  }
  if (Number.isInteger(toolArgs.max) && (toolArgs.max < 1 || toolArgs.max > 20)) {
    throw new Error("max debe ser un entero de 1 a 20; el precio de búsqueda actual es 0.08 USDC.");
  }

  const paymentClient = new x402Client();
  const signer = privateKeyToAccount(privateKey);
  registerExactEvmScheme(paymentClient, { signer });

  const mcpClient = new Client({ name: "tiktok-bridge-paid-client", version: "1.0.0" });
  await mcpClient.connect(
    new StreamableHTTPClientTransport(new URL(BAZAAR_MCP))
  );
  const paidClient = createX402MCPClient(mcpClient, paymentClient, {
    autoPayment: true,
    onPaymentRequested: async (req) => {
      // El proceso solo arranca con consentimiento explícito vía env var.
      console.error("x402 payment requested:", {
        price: req.price,
        network: req.network,
      });
      return process.env.TIKTOK_BRIDGE_ALLOW_LIVE_PAYMENT === "YES";
    },
  });

  try {
    const discovery = await paidClient.callTool("search_resources", {
      query: searchQuery,
    });
    console.log("Bazaar discovery:");
    console.log(JSON.stringify(discovery, null, 2));
    console.error("Calling paid resource:", toolName);
    const result = await paidClient.callTool("proxy_tool_call", {
      toolName,
      ...toolArgs,
    });
    console.log(JSON.stringify(result, null, 2));
  } finally {
    await mcpClient.close();
  }
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : "Error desconocido");
  process.exitCode = 1;
});
