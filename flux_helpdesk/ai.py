"""Answers from the Flux knowledge bot (github.com/RunOnFlux/ownllm, the docs assistant).

Two entry points:
- ask: the "Ask Flux AI" box on /support, open to guests and rate limited.
- suggest_reply: the agent's "Ask Flux AI" button on a ticket.

The support bot that answers tickets by itself (influx-agents) is a separate,
private service. It talks to Helpdesk through the API and is not part of this
app.
"""

import re

import frappe
import requests
from frappe import _
from frappe.rate_limiter import rate_limit

from flux_helpdesk.utils import get_settings, html_to_text, truncate

MAX_QUESTION = 1000
TIMEOUT = 90
# The bot cites its passages as [1], [2, 3]; the numbers mean nothing once
# sources without a link are dropped, so the markers go.
_CITATION = re.compile(r"\s*\[\d+(?:\s*,\s*\d+)*\]")


def clean_answer(answer: str | None) -> str:
    return _CITATION.sub("", answer or "").strip()


def clean_sources(sources: list | None) -> list[dict]:
    cleaned, seen = [], set()
    for source in sources or []:
        url = (source or {}).get("url") or ""
        if not url.startswith(("https://", "http://")) or url in seen:
            continue
        seen.add(url)
        title = source.get("heading") or source.get("title") or source.get("source") or url
        cleaned.append({"title": truncate(str(title), 120), "url": url})
    return cleaned[:5]


def ask_knowledge_bot(question: str) -> dict:
    settings = get_settings()
    base = (settings.knowledge_bot_url or "").rstrip("/")
    if not base:
        frappe.throw(_("The knowledge bot is not set up yet."))

    headers = {"Content-Type": "application/json"}
    api_key = settings.get_password("knowledge_bot_api_key", raise_exception=False)
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        response = requests.post(
            f"{base}/ask",
            json={"question": question, "stream": False},
            headers=headers,
            timeout=TIMEOUT,
        )
    except requests.RequestException:
        frappe.throw(_("Flux AI is not reachable right now. Please try again in a minute."))

    if response.status_code == 429:
        frappe.throw(_("Flux AI is busy. Please try again in a minute."))
    if not response.ok:
        frappe.logger("flux_helpdesk").warning(f"knowledge bot answered HTTP {response.status_code}")
        frappe.throw(_("Flux AI could not answer this one. Please open a ticket instead."))

    data = response.json()
    return {
        "answer": clean_answer(data.get("answer")),
        "sources": clean_sources(data.get("sources")),
    }


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=10, seconds=60)
def ask(question: str, product: str | None = None) -> dict:
    if not get_settings().ask_ai_on_support_page:
        frappe.throw(_("Ask AI is turned off."), frappe.PermissionError)

    question = (question or "").strip()
    if len(question) < 3:
        frappe.throw(_("Please describe the problem in a few words."))
    question = question[:MAX_QUESTION]

    prompt = f"{question}\n\n(Product: {product.strip()[:40]})" if product else question
    return ask_knowledge_bot(prompt)


@frappe.whitelist(methods=["POST"])
def suggest_reply(ticket: str) -> dict:
    from helpdesk.utils import is_agent

    if not is_agent():
        frappe.throw(_("Only agents can ask for a suggested reply."), frappe.PermissionError)
    if not get_settings().ask_ai_in_agent_view:
        frappe.throw(_("Ask Flux AI is turned off for agents."), frappe.PermissionError)
    frappe.has_permission("HD Ticket", "read", ticket, throw=True)

    subject, description = frappe.db.get_value("HD Ticket", ticket, ["subject", "description"])
    latest = frappe.get_all(
        "Communication",
        filters={
            "reference_doctype": "HD Ticket",
            "reference_name": ticket,
            "sent_or_received": "Received",
        },
        fields=["content"],
        order_by="creation desc",
        limit=1,
    )
    message = html_to_text(latest[0].content if latest else description, 1500)
    return ask_knowledge_bot(f"{subject}\n\n{message}".strip())
