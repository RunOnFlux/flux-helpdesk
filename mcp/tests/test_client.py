import json

import pytest

from flux_helpdesk_mcp.client import HelpdeskClient, HelpdeskError, html_to_text
from flux_helpdesk_mcp.server import _as_html


class FakeResponse:
    def __init__(self, status=200, payload=None):
        self.status_code = status
        self.ok = 200 <= status < 300
        self._payload = payload or {}

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, responses):
        self.headers = {}
        self.responses = list(responses)
        self.requests = []

    def request(self, method, url, **kwargs):
        self.requests.append((method, url, kwargs))
        return self.responses.pop(0)


def make(responses):
    session = FakeSession(responses)
    return HelpdeskClient("https://support.example", "key", "secret", session=session), session


def test_token_auth_header():
    _, session = make([])
    assert session.headers["Authorization"] == "token key:secret"


def test_rejects_non_http_url():
    with pytest.raises(HelpdeskError):
        HelpdeskClient("support.example", "k", "s", session=FakeSession([]))


def test_search_builds_filters_and_parses_assignees():
    client, session = make([FakeResponse(payload={"data": [{"name": "0003", "_assign": '["a@x.io"]'}]})])
    rows = client.search_tickets("node", status="Open", product="FluxNodes", limit=500)
    method, url, kwargs = session.requests[0]
    assert (method, url) == ("GET", "https://support.example/api/resource/HD Ticket")
    filters = json.loads(kwargs["params"]["filters"])
    assert ["subject", "like", "%node%"] in filters
    assert ["flux_product", "=", "FluxNodes"] in filters
    assert kwargs["params"]["limit_page_length"] == 100
    assert rows == [{"name": "0003", "assigned_to": ["a@x.io"]}]


def test_doc_method_sends_kwargs_as_json():
    client, session = make([FakeResponse(payload={"message": None})])
    client.add_note("0003", "<p>hi</p>")
    _, url, kwargs = session.requests[0]
    assert url.endswith("/api/method/run_doc_method")
    assert kwargs["json"]["method"] == "new_comment"
    assert json.loads(kwargs["json"]["args"]) == {"content": "<p>hi</p>"}


def test_server_message_becomes_error():
    messages = json.dumps([json.dumps({"message": "Unable to send email."})])
    client, _ = make(
        [
            FakeResponse(payload={"data": {"raised_by": "c@example.com"}}),
            FakeResponse(417, {"_server_messages": messages}),
        ]
    )
    with pytest.raises(HelpdeskError, match="Unable to send email"):
        client.reply("0003", "<p>x</p>")


def test_reply_is_addressed_to_the_customer():
    client, session = make(
        [FakeResponse(payload={"data": {"raised_by": "c@example.com"}}), FakeResponse(payload={})]
    )
    client.reply("0003", "<p>x</p>")
    _, url, kwargs = session.requests[1]
    assert url.endswith("/api/method/run_doc_method")
    assert kwargs["json"]["method"] == "reply_via_agent"
    assert json.loads(kwargs["json"]["args"]) == {"message": "<p>x</p>", "to": "c@example.com"}


def test_get_ticket_reads_helpdesk_ticket_view():
    payload = {
        "message": {
            "name": "0003",
            "subject": "Node down",
            "raised_by": "c@example.com",
            "_assign": '["a@x.io"]',
            "description": "<p>Help</p>",
            "communications": [
                {"sender": "c@example.com", "sent_or_received": "Received", "content": "<p>Help</p>"},
                {"sender": "a@x.io", "sent_or_received": "Sent", "content": "<p>On it</p>"},
            ],
            "comments": [{"commented_by": "a@x.io", "creation": "2026-10-15", "content": "<p>note</p>"}],
        }
    }
    client, session = make([FakeResponse(payload=payload)])
    ticket = client.get_ticket("0003")
    method, url, kwargs = session.requests[0]
    assert url.endswith("/api/method/helpdesk.helpdesk.doctype.hd_ticket.api.get_one")
    assert kwargs["json"] == {"name": "0003"}
    assert ticket["ticket"]["assigned_to"] == ["a@x.io"]
    assert [m["direction"] for m in ticket["messages"]] == ["customer", "agent"]
    assert ticket["internal_notes"] == [{"by": "a@x.io", "at": "2026-10-15", "text": "note"}]


def test_auth_failure_is_explained():
    client, _ = make([FakeResponse(401)])
    with pytest.raises(HelpdeskError, match="API key"):
        client.get_ticket("1")


def test_permission_failure_is_not_blamed_on_the_key():
    client, _ = make([FakeResponse(403)])
    with pytest.raises(HelpdeskError, match="Not permitted"):
        client.get_ticket("1")


def test_html_to_text_and_back():
    assert html_to_text("<p>Hi</p><script>x</script><p>there</p>") == "Hi\n\nthere"
    assert _as_html("a <b>\n\nsecond\nline") == "<p>a &lt;b&gt;</p><p>second<br>line</p>"
