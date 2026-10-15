"""A thin client for the Frappe Helpdesk REST API, used by the MCP tools."""

import json
import re
from html.parser import HTMLParser

import requests

TICKET_FIELDS = [
    "name",
    "subject",
    "status",
    "priority",
    "agent_group",
    "flux_product",
    "raised_by",
    "creation",
    "modified",
    "_assign",
]


class HelpdeskError(Exception):
    pass


class _TextExtractor(HTMLParser):
    BLOCKS = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "blockquote"}

    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        elif tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip:
            self._skip -= 1
        elif tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def html_to_text(html: str | None, limit: int = 4000) -> str:
    if not html:
        return ""
    parser = _TextExtractor()
    parser.feed(html)
    text = "".join(parser.parts)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text).strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


class HelpdeskClient:
    def __init__(self, url: str, api_key: str, api_secret: str, session: requests.Session | None = None):
        if not url.startswith(("https://", "http://")):
            raise HelpdeskError("FLUX_HELPDESK_URL must start with https://")
        self.url = url.rstrip("/")
        self.session = session or requests.Session()
        self.session.headers.update(
            {"Authorization": f"token {api_key}:{api_secret}", "Accept": "application/json"}
        )

    # Transport -------------------------------------------------------------

    def _request(self, method: str, path: str, **kwargs):
        response = self.session.request(method, f"{self.url}{path}", timeout=60, **kwargs)
        if response.status_code == 401:
            raise HelpdeskError("Helpdesk refused the API key (check the key and secret).")
        if response.status_code == 403:
            raise HelpdeskError(
                _server_message(response)
                or "Not permitted (the API user needs the Agent role and access to this ticket's team)."
            )
        if response.status_code == 404:
            raise HelpdeskError("Not found.")
        if not response.ok:
            raise HelpdeskError(_server_message(response) or f"Helpdesk answered HTTP {response.status_code}")
        return response.json()

    def get_list(self, doctype: str, fields: list[str], filters: list | None = None, **params):
        query = {"fields": json.dumps(fields), "filters": json.dumps(filters or [])}
        query.update({k: v for k, v in params.items() if v is not None})
        return self._request("GET", f"/api/resource/{doctype}", params=query)["data"]

    def call(self, endpoint: str, /, **kwargs):
        return self._request("POST", f"/api/method/{endpoint}", json=kwargs).get("message")

    def run_doc_method(self, doctype: str, name: str, method: str, **kwargs):
        return self.call("run_doc_method", dt=doctype, dn=name, method=method, args=json.dumps(kwargs))

    # Tickets ---------------------------------------------------------------

    def search_tickets(
        self,
        query: str = "",
        status: str | None = None,
        team: str | None = None,
        product: str | None = None,
        priority: str | None = None,
        limit: int = 20,
    ) -> list[dict]:
        filters = []
        if query:
            filters.append(["subject", "like", f"%{query}%"])
        for field, value in (
            ("status", status),
            ("agent_group", team),
            ("flux_product", product),
            ("priority", priority),
        ):
            if value:
                filters.append([field, "=", value])
        rows = self.get_list(
            "HD Ticket",
            TICKET_FIELDS,
            filters,
            order_by="modified desc",
            limit_page_length=max(1, min(limit, 100)),
        )
        for row in rows:
            row["assigned_to"] = json.loads(row.pop("_assign") or "[]")
        return rows

    def get_ticket(self, ticket: str) -> dict:
        # Helpdesk's own ticket endpoint applies its agent and team permissions, unlike
        # /api/resource/Communication, which hides email messages from plain agents.
        doc = self.call("helpdesk.helpdesk.doctype.hd_ticket.api.get_one", name=ticket)
        assigned = doc.get("_assign")
        return {
            "ticket": {key: doc.get(key) for key in TICKET_FIELDS if key != "_assign"}
            | {
                "assigned_to": json.loads(assigned) if isinstance(assigned, str) else assigned or [],
                "description": html_to_text(doc.get("description")),
            },
            "messages": [
                {
                    "from": m.get("sender"),
                    "direction": "customer" if m.get("sent_or_received") == "Received" else "agent",
                    "at": m.get("communication_date") or m.get("creation"),
                    "text": html_to_text(m.get("content")),
                }
                for m in doc.get("communications") or []
            ],
            "internal_notes": [
                {"by": n.get("commented_by"), "at": n.get("creation"), "text": html_to_text(n.get("content"))}
                for n in doc.get("comments") or []
            ],
        }

    def reply(self, ticket: str, message_html: str):
        # Helpdesk only emails the addresses in `to`; its own reply box fills in the customer.
        raised_by = self._request("GET", f"/api/resource/HD Ticket/{ticket}")["data"].get("raised_by")
        if not raised_by:
            raise HelpdeskError(f"Ticket {ticket} has no customer email to reply to.")
        return self.run_doc_method("HD Ticket", ticket, "reply_via_agent", message=message_html, to=raised_by)

    def add_note(self, ticket: str, note_html: str):
        return self.run_doc_method("HD Ticket", ticket, "new_comment", content=note_html)

    def update_ticket(self, ticket: str, values: dict) -> dict:
        return self._request("PUT", f"/api/resource/HD Ticket/{ticket}", json=values)["data"]

    def assign(self, ticket: str, agent_email: str):
        return self.call(
            "frappe.desk.form.assign_to.add",
            doctype="HD Ticket",
            name=ticket,
            assign_to=[agent_email],
        )

    # Knowledge -------------------------------------------------------------

    def search_articles(self, query: str, limit: int = 10) -> list[dict]:
        rows = self.get_list(
            "HD Article",
            ["name", "title", "content", "category"],
            [["status", "=", "Published"]],
            or_filters=json.dumps([["title", "like", f"%{query}%"], ["content", "like", f"%{query}%"]]),
            limit_page_length=max(1, min(limit, 50)),
        )
        return [
            {
                "title": r["title"],
                "url": f"{self.url}/helpdesk/kb-public/articles/{r['name']}",
                "text": html_to_text(r["content"], 1500),
            }
            for r in rows
        ]

    def ask_knowledge_bot(self, question: str) -> dict:
        return self.call("flux_helpdesk.ai.ask", question=question)


def _server_message(response) -> str | None:
    try:
        data = response.json()
        messages = json.loads(data.get("_server_messages") or "[]")
        if messages:
            return json.loads(messages[0]).get("message")
        return data.get("exception")
    except ValueError:
        return None
