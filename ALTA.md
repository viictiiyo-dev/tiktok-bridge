# Alta TikTok Bridge (réplica del footprint Veredicto)

Todo lo marcable lo haces tú con tu cuenta; lo técnico ya está vivo y verificado.

## 0. URLs públicas (verificadas 200 el 2026-10-11)

- `https://veredicto.dpdns.org/v1/tiktok/search` — 402 con payTo + bazaar extension
- `https://veredicto.dpdns.org/tiktok/llms.txt`
- `https://veredicto.dpdns.org/tiktok/skill.md`
- `https://veredicto.dpdns.org/tiktok/agent-card.json`
- `https://veredicto.dpdns.org/tiktok/terms`
- `https://veredicto.dpdns.org/tiktok-mcp/mcp` — MCP Streamable HTTP (tools: tiktok_search, tiktok_perfil_info, tiktok_comments_info)

## 1. Altas (por orden de valor)

1. **A2A Registry** — nueva ficha de agente con `https://veredicto.dpdns.org/tiktok/agent-card.json` (no dupliques la de Veredicto; es segundo agente misma org). Reclama igual que la anterior.
2. **Smithery** — publica `tiktok-bridge` (nuevo namespace o mismo owner `viictiiyo`): URL MCP `https://veredicto.dpdns.org/tiktok-mcp/mcp`, 3 tools. Descripción corta: "Pay-per-call TikTok search for agents, $0.08 via x402 on Base. No API key."
3. **GitHub `viictiiyo-dev/veredicto-skills`** — añade `tiktok/SKILL.md` (copia de `TIKTOK/SKILL.md`) para el flujo `npx skills add`.
4. **agentskill.sh** — envía `https://veredicto.dpdns.org/tiktok/skill.md`.
5. **x402-list** — nuevo submit del endpoint (el anterior era solo Veredicto).
6. **Glama** — connector manual a `https://veredicto.dpdns.org/tiktok-mcp/mcp`.
7. **PulseMCP** — submit con endpoint + tools + landing (usa llms.txt como descripción).
8. **Delegare/agentic.market** — registra merchant `0x139a680FCa575cfA5ADA25b5417fe9fDeE8ED06E` con las 3 rutas y precios.
9. **Sitemap** — declara las 4 URLs en Search Console (requiere tu cuenta).

## 2. Copy-paste descripción (directorios)

> TikTok Bridge: pay-per-call TikTok search for AI agents. POST /v1/tiktok/search, $0.08 USDC via x402 on Base mainnet, no account or API key. Free-miss if no results. 2 real on-chain sales verified. MCP: /tiktok-mcp/mcp.

## 3. Verificación post-alta (mía cuando me digas)

- [ ] Ficha A2A responde 200 con skill `tiktok-search`
- [ ] Smithery lista el server y `tools/list` vía MCP público devuelve 3 tools
- [ ] CDP discovery incluye payTo `0x139a…ED06E` en ruta tiktok
- [ ] Primera venta de un tercero (ledger + tx)
