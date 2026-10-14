"""MCP server for Flux Helpdesk.

Gives an AI agent (Claude Code, Claude Desktop, any MCP client) the same tools a
support agent has: find and read tickets, write internal notes, reply, change
status, priority or team, assign, and look things up in the help centre or the
Flux knowledge bot.

It acts as one Helpdesk user, through that user's API key, so Helpdesk's own
permissions decide what it can see and do. Use a dedicated agent account.

Configuration (environment):
    FLUX_HELPDESK_URL         e.g. https://support.runonflux.io
    FLUX_HELPDESK_API_KEY     from the user's API Access settings
    FLUX_HELPDESK_API_SECRET
    FLUX_HELPDESK_READ_ONLY   "1" to hide every tool that changes something
"""

import html
import os

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from flux_helpdesk_mcp.client import HelpdeskClient

READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)
WRITES = ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=False)
SENDS_EMAIL = ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=True)

server = MCPServer(
    name="flux-helpdesk",
    title="Flux Helpdesk",
    instructions=(
        "Tools for Flux's support desk. Read the whole ticket before acting. Prefer an internal "
        "note when unsure; reply_to_ticket emails the customer. Never ask a customer for a seed "
        "phrase, private key or password, and never promise refunds: leave those to a person."
    ),
)

_client: HelpdeskClient | None = None


def client() -> HelpdeskClient:
    global _client
    if _client is None:
        missing = [
            name
            for name in ("FLUX_HELPDESK_URL", "FLUX_HELPDESK_API_KEY", "FLUX_HELPDESK_API_SECRET")
            if not os.environ.get(name)
        ]
        if missing:
            raise RuntimeError(f"Set {', '.join(missing)} to use the Flux Helpdesk tools.")
        _client = HelpdeskClient(
            os.environ["FLUX_HELPDESK_URL"],
            os.environ["FLUX_HELPDESK_API_KEY"],
            os.environ["FLUX_HELPDESK_API_SECRET"],
        )
    return _client


def _as_html(text: str) -> str:
    paragraphs = [p.strip() for p in text.strip().split("\n\n") if p.strip()]
    return "".join(f"<p>{html.escape(p).replace(chr(10), '<br>')}</p>" for p in paragraphs)


@server.tool(annotations=READ_ONLY)
def search_tickets(
    query: str = "",
    status: str | None = None,
    team: str | None = None,
    product: str | None = None,
    priority: str | None = None,
    limit: int = 20,
) -> list[dict]:
    """Find tickets, newest activity first.

    query matches the subject. status is e.g. Open, Replied, Resolved, Closed. team is the
    Helpdesk team name, product e.g. FluxNodes or Flux Games, priority Low/Medium/High/Urgent.
    """
    return client().search_tickets(query, status, team, product, priority, limit)


@server.tool(annotations=READ_ONLY)
def get_ticket(ticket: str) -> dict:
    """One ticket with its full conversation (customer and agent messages) and internal notes."""
    return client().get_ticket(ticket)


@server.tool(annotations=READ_ONLY)
def search_help_articles(query: str, limit: int = 10) -> list[dict]:
    """Published help-centre articles whose title or text contains the query."""
    return client().search_articles(query, limit)


@server.tool(annotations=READ_ONLY)
def ask_knowledge_bot(question: str) -> dict:
    """Ask the Flux knowledge bot (answers from docs.runonflux.com). Returns answer and sources."""
    return client().ask_knowledge_bot(question)


@server.tool(annotations=WRITES)
def add_internal_note(ticket: str, note: str) -> str:
    """Add a private note to a ticket. Only the team sees it; the customer is not emailed."""
    client().add_note(ticket, _as_html(note))
    return f"Note added to #{ticket}."


@server.tool(annotations=SENDS_EMAIL)
def reply_to_ticket(ticket: str, message: str) -> str:
    """Reply to the customer. This EMAILS the customer from the support address. Plain text."""
    client().reply(ticket, _as_html(message))
    return f"Reply sent on #{ticket}."


@server.tool(annotations=WRITES)
def update_ticket(
    ticket: str,
    status: str | None = None,
    priority: str | None = None,
    team: str | None = None,
    product: str | None = None,
) -> dict:
    """Change a ticket's status, priority, team or product. Unset arguments stay as they are."""
    values = {
        key: value
        for key, value in (
            ("status", status),
            ("priority", priority),
            ("agent_group", team),
            ("flux_product", product),
        )
        if value
    }
    if not values:
        return {"changed": False}
    updated = client().update_ticket(ticket, values)
    return {"changed": True, **{key: updated.get(key) for key in values}}


@server.tool(annotations=WRITES)
def assign_ticket(ticket: str, agent_email: str) -> str:
    """Assign a ticket to an agent by their email address."""
    client().assign(ticket, agent_email)
    return f"#{ticket} assigned to {agent_email}."


if os.environ.get("FLUX_HELPDESK_READ_ONLY") == "1":
    for _name in ("add_internal_note", "reply_to_ticket", "update_ticket", "assign_ticket"):
        server.remove_tool(_name)


def main():
    server.run()


if __name__ == "__main__":
    main()
