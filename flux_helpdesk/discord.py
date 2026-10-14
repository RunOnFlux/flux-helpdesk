"""Ticket alerts in the team's Discord channel.

Posts through a channel webhook: a card for each new ticket, each customer
reply and each ticket raised to Urgent. Customer text is never allowed to ping
anyone (allowed_mentions parse is empty); the only ping is the role configured
for urgent tickets.

The support bot (influx-agents) posts its own AI triage cards in the same
channel. Turn off "New tickets" here if both would say the same thing.
"""

import re
import time
from datetime import datetime, timezone

import frappe
import requests

from flux_helpdesk.utils import agent_ticket_url, get_settings, html_to_text, truncate

COLORS = {
    "new": 0x2656D7,  # Flux blue
    "reply": 0x5679FF,  # Flux secondary
    "urgent": 0xEF4444,
}
HEADLINES = {
    "new": "New ticket",
    "reply": "Customer replied",
    "urgent": "Raised to Urgent",
}
_MARKDOWN = re.compile(r"([\\*_~`|>\[\]()#])")


def escape_markdown(text: str) -> str:
    return _MARKDOWN.sub(r"\\\1", text or "")


def build_payload(
    event: str,
    *,
    name: str,
    subject: str,
    excerpt: str,
    url: str,
    team: str | None = None,
    priority: str | None = None,
    product: str | None = None,
    status: str | None = None,
    role_id: str | None = None,
    timestamp: str | None = None,
) -> dict:
    fields = [
        {"name": label, "value": escape_markdown(truncate(value, 100)), "inline": True}
        for label, value in (
            ("Team", team),
            ("Priority", priority),
            ("Product", product),
            ("Status", status),
        )
        if value
    ]
    embed = {
        "author": {"name": HEADLINES[event]},
        "title": truncate(f"#{name} · {subject or '(no subject)'}", 256),
        "url": url,
        "description": escape_markdown(truncate(excerpt, 600)) or None,
        "color": COLORS[event],
        "fields": fields,
        "footer": {"text": "Flux Helpdesk"},
        "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
    }
    payload = {
        "username": "Flux Helpdesk",
        "embeds": [{k: v for k, v in embed.items() if v not in (None, [])}],
        "allowed_mentions": {"parse": [], "roles": [role_id] if role_id else []},
    }
    if role_id:
        payload["content"] = f"<@&{role_id}>"
    return payload


def message_link(guild_id: str | None, message: dict) -> str | None:
    channel_id, message_id = message.get("channel_id"), message.get("id")
    if not (guild_id and channel_id and message_id):
        return None
    return f"https://discord.com/channels/{guild_id}/{channel_id}/{message_id}"


# Document events
# ---------------


def _muted() -> bool:
    flags = frappe.flags
    return bool(
        flags.in_import or flags.in_migrate or flags.in_install or flags.in_patch or flags.flux_importing
    )


def _wants(setting: str) -> bool:
    if _muted():
        return False
    settings = get_settings()
    return bool(settings.discord_enabled and settings.get(setting))


def _enqueue(event: str, ticket: str, communication: str | None = None):
    frappe.enqueue(
        "flux_helpdesk.discord.send_event",
        queue="short",
        enqueue_after_commit=True,
        event=event,
        ticket=ticket,
        communication=communication,
    )


def on_ticket_insert(doc, method=None):
    if _wants("notify_new_ticket"):
        _enqueue("new", doc.name)


def on_ticket_update(doc, method=None):
    if doc.is_new() or not doc.has_value_changed("priority"):
        return
    if (doc.priority or "").lower() == "urgent" and _wants("notify_urgent"):
        _enqueue("urgent", doc.name)


def on_communication_insert(doc, method=None):
    if doc.reference_doctype != "HD Ticket" or not doc.reference_name:
        return
    if doc.communication_type != "Communication" or doc.sent_or_received != "Received":
        return
    if not _wants("notify_customer_reply"):
        return
    # The first received email is the one that opened the ticket; "New ticket" covers it.
    received = frappe.db.count(
        "Communication",
        {
            "reference_doctype": "HD Ticket",
            "reference_name": doc.reference_name,
            "sent_or_received": "Received",
        },
    )
    if received > 1:
        _enqueue("reply", doc.reference_name, doc.name)


# Background job
# --------------


def send_event(event: str, ticket: str, communication: str | None = None):
    settings = get_settings()
    webhook = settings.get_password("discord_webhook_url", raise_exception=False)
    if not (settings.discord_enabled and webhook):
        return

    doc = frappe.get_doc("HD Ticket", ticket)
    if communication:
        excerpt = html_to_text(frappe.db.get_value("Communication", communication, "content"), 600)
    else:
        excerpt = html_to_text(doc.description, 600)

    payload = build_payload(
        event,
        name=doc.name,
        subject=doc.subject,
        excerpt=excerpt,
        url=agent_ticket_url(doc.name),
        team=doc.agent_group,
        priority=doc.priority,
        product=doc.get("flux_product"),
        status=doc.status if event != "new" else None,
        role_id=(settings.discord_role_id or None) if event == "urgent" else None,
    )
    message = post_webhook(webhook, payload)

    if event == "new" and message and doc.meta.has_field("flux_discord_url"):
        link = message_link(settings.discord_guild_id, message)
        if link:
            doc.db_set("flux_discord_url", link, update_modified=False)


def post_webhook(webhook: str, payload: dict, attempts: int = 2) -> dict | None:
    """POST to the webhook and return Discord's message, or None. Logs never include the URL."""
    for attempt in range(attempts):
        try:
            response = requests.post(f"{webhook}?wait=true", json=payload, timeout=10)
        except requests.RequestException as exc:
            frappe.logger("flux_helpdesk").warning(f"Discord webhook unreachable: {exc.__class__.__name__}")
            return None
        if response.status_code == 429 and attempt + 1 < attempts:
            retry_after = float(response.json().get("retry_after", 1))
            time.sleep(min(retry_after, 5))
            continue
        if response.ok:
            return response.json()
        frappe.logger("flux_helpdesk").warning(
            f"Discord webhook refused the post: HTTP {response.status_code}"
        )
        return None
    return None
