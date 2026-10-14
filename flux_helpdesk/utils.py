"""Small helpers shared by the theme, AI and Discord code.

Everything here that does not need a site is plain Python, so the unit tests
can run without a bench.
"""

import re

DEFAULT_PRODUCTS = [
    "FluxCloud",
    "FluxNodes",
    "FluxEdge",
    "Flux Games",
    "FluxAI",
    "ZelCore",
    "SSP Wallet",
]

_WHITESPACE = re.compile(r"[ \t\r\f\v]+")
_BLANK_LINES = re.compile(r"\n{3,}")


def html_to_text(html: str | None, limit: int | None = None) -> str:
    """Readable plain text from ticket or email HTML."""
    if not html:
        return ""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "head"]):
        tag.decompose()
    # Quoted history in email replies repeats the whole thread.
    for quote in soup.select("blockquote, .gmail_quote, .replied-content"):
        quote.decompose()
    for br in soup.find_all("br"):
        br.replace_with("\n")
    for block in soup.find_all(["p", "div", "li", "tr", "h1", "h2", "h3", "h4"]):
        block.insert_after("\n")

    text = soup.get_text()
    text = "\n".join(_WHITESPACE.sub(" ", line).strip() for line in text.splitlines())
    text = _BLANK_LINES.sub("\n\n", text).strip()
    return truncate(text, limit) if limit else text


def truncate(text: str, limit: int) -> str:
    text = text or ""
    if len(text) <= limit:
        return text
    return text[: max(limit - 1, 0)].rstrip() + "…"


def parse_products(raw: str | None) -> list[str]:
    products = [line.strip() for line in (raw or "").splitlines() if line.strip()]
    return products or list(DEFAULT_PRODUCTS)


def get_settings():
    import frappe

    return frappe.get_cached_doc("Flux Helpdesk Settings")


def agent_ticket_url(ticket: str) -> str:
    import frappe

    return f"{frappe.utils.get_url()}/helpdesk/tickets/{ticket}"
