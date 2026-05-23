# Moved

The **MCP Confirmation System** design document lives in the main Geoportal monorepo:

**[docs/04_development/sdk/mcp_confirmation_system.md](../docs/04_development/sdk/mcp_confirmation_system.md)**

Quick reference:

- Operator CLI: `geopack-sdk-confirm approve <confirmation_id>`
- Store: `~/.geopack/mcp_confirmations.json` (or `GEOPACK_CONFIRM_STORE`)
- Tests: `python -m unittest tests.test_confirmation_security_fix -v`
