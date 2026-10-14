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
    client, _ = make([FakeResponse(417, {"_server_messages": messages})])
    with pytest.raises(HelpdeskError, match="Unable to send email"):
        client.reply("0003", "<p>x</p>")


def test_auth_failure_is_explained():
    client, _ = make([FakeResponse(403)])
    with pytest.raises(HelpdeskError, match="API key"):
        client.get_ticket("1")


def test_html_to_text_and_back():
    assert html_to_text("<p>Hi</p><script>x</script><p>there</p>") == "Hi\n\nthere"
    assert _as_html("a <b>\n\nsecond\nline") == "<p>a &lt;b&gt;</p><p>second<br>line</p>"
