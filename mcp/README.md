# Flux Helpdesk MCP server

Lets an AI agent work the support desk through the [Model Context Protocol](https://modelcontextprotocol.io): Claude Code, Claude Desktop or any MCP client.

| Tool | What it does | Changes anything? |
|---|---|---|
| `search_tickets` | Find tickets by subject, status, team, product, priority | No |
| `get_ticket` | A ticket with every message and internal note, as plain text | No |
| `search_help_articles` | Published help-centre articles | No |
| `ask_knowledge_bot` | The Flux docs assistant's answer, with sources | No |
| `add_internal_note` | Private note; the customer sees nothing | Yes |
| `update_ticket` | Status, priority, team, product | Yes |
| `assign_ticket` | Assign to an agent by email | Yes |
| `reply_to_ticket` | **Emails the customer** | Yes |

It acts as one Helpdesk user through that user's API key, so Helpdesk's permissions apply. Create a dedicated agent (for example "AI Assistant"), then **User → Settings → API Access → Generate keys**.

## Install

```bash
pip install "git+https://github.com/RunOnFlux/flux-helpdesk#subdirectory=mcp"
```

## Configure

| Variable | Example |
|---|---|
| `FLUX_HELPDESK_URL` | `https://support.runonflux.io` |
| `FLUX_HELPDESK_API_KEY` | from API Access |
| `FLUX_HELPDESK_API_SECRET` | from API Access |
| `FLUX_HELPDESK_READ_ONLY` | `1` hides every tool that changes something |

Claude Code:

```bash
claude mcp add flux-helpdesk \
  -e FLUX_HELPDESK_URL=https://support.runonflux.io \
  -e FLUX_HELPDESK_API_KEY=... -e FLUX_HELPDESK_API_SECRET=... \
  -- flux-helpdesk-mcp
```

Claude Desktop (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "flux-helpdesk": {
      "command": "flux-helpdesk-mcp",
      "env": {
        "FLUX_HELPDESK_URL": "https://support.runonflux.io",
        "FLUX_HELPDESK_API_KEY": "...",
        "FLUX_HELPDESK_API_SECRET": "..."
      }
    }
  }
}
```

Start read-only (`FLUX_HELPDESK_READ_ONLY=1`) until you trust how it is used. Tools carry MCP hints (read-only, open-world for the one that emails) so clients can ask before running them.

## Develop

```bash
pip install -e ".[test]"
pytest
```
