#!/usr/bin/env python3
"""TikTok Bridge como servidor MCP (stdio o Streamable HTTP).
Uso local / Smithery:
  claude mcp add tiktok-bridge --transport stdio -- "C:\\Program Files\\Python311\\python.exe" src/mcp_server.py
  python src/mcp_server.py --http --port 41245
tiktok_search usa el router en local (sin paywall, uso del operador).
tiktok_perfil_info / tiktok_comments_info describen los endpoints de pago; no liquidan.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mcp.server.mcpserver import MCPServer

mcp = MCPServer("tiktok-bridge")


@mcp.tool()
def tiktok_search(q: str, max_results: int = 20) -> str:
    """Busca videos publicos de TikTok. q: consulta. max_results 1-50. Solo publico, sin login."""
    import tiktok_router as router
    status, data = router.run_search(q, max(1, min(50, max_results)))
    if status == "retry":
        return "TikTok ocupado (captcha). Reintenta en 60s: " + data.get("retry_hint", "")
    vids = data.get("videos", [])
    if not vids:
        return "Sin resultados (free-miss)."
    lines = [f"{len(vids)} videos para '{q}':"]
    for v in vids[:20]:
        lines.append(f"- {v.get('id')}: {v.get('desc','')[:120]} | {v.get('autor')} | likes {v.get('likes')}")
    return "\n".join(lines)


@mcp.tool()
def tiktok_perfil_info(user: str) -> str:
    """Info del endpoint de pago POST /v1/tiktok/perfil (0.08 USDC, x402 Base). No liquida pagos."""
    return ("POST https://veredicto.dpdns.org/v1/tiktok/perfil {user} — 0.08 USDC por llamada "
            f"en Base mainnet vía x402. Ejemplo user='{user}'. Solo perfiles publicos.")


@mcp.tool()
def tiktok_comments_info(video_id: str) -> str:
    """Info del endpoint de pago POST /v1/tiktok/comments (0.05 USDC, x402 Base). No liquida pagos."""
    return ("POST https://veredicto.dpdns.org/v1/tiktok/comments {id, max} — 0.05 USDC por llamada "
            f"en Base mainnet vía x402. Ejemplo id='{video_id}'. Solo comentarios publicos.")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="TikTok Bridge MCP")
    p.add_argument("--http", action="store_true", help="Streamable HTTP en vez de stdio")
    p.add_argument("--port", type=int, default=41245)
    a = p.parse_args()
    if a.http:
        mcp.run(transport="streamable-http", host="127.0.0.1", port=a.port)
    else:
        mcp.run()
