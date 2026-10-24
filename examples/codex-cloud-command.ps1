$env:OPENMOUSE_MCP_TOKEN = "replace-with-the-same-http-token"

codex mcp add openmouse-cloud `
  --url "https://your-authenticated-domain.example/mcp" `
  --bearer-token-env-var OPENMOUSE_MCP_TOKEN

codex mcp get openmouse-cloud --json
