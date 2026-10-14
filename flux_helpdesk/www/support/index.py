import frappe

from flux_helpdesk import __version__
from flux_helpdesk.utils import get_settings, parse_products

no_cache = 1

# Helpdesk groups its statuses into three categories; customers see plain words.
STATUS_LABELS = {
    "Open": ("With our team", "open"),
    "Paused": ("Waiting on you", "paused"),
    "Resolved": ("Solved", "resolved"),
}


def get_context(context):
    settings = get_settings()
    user = frappe.session.user
    logged_in = user != "Guest"

    context.no_cache = 1
    context.flux_version = __version__
    context.csrf_token = frappe.sessions.get_csrf_token() if logged_in else ""
    context.logged_in = logged_in
    context.first_name = frappe.db.get_value("User", user, "first_name") if logged_in else None
    context.products = parse_products(settings.support_products)
    context.ask_ai = bool(settings.ask_ai_on_support_page)
    context.discord_invite_url = settings.discord_invite_url
    context.status_page_url = settings.status_page_url
    context.articles = popular_articles()
    context.tickets = recent_tickets(user) if logged_in else []
    return context


def popular_articles(limit: int = 6) -> list[dict]:
    return frappe.get_all(
        "HD Article",
        filters={"status": "Published"},
        fields=["name", "title"],
        order_by="views desc, modified desc",
        limit=limit,
    )


def recent_tickets(user: str, limit: int = 5) -> list[dict]:
    tickets = frappe.get_all(
        "HD Ticket",
        filters={"raised_by": user},
        fields=["name", "subject", "status_category", "modified", "flux_product"],
        order_by="modified desc",
        limit=limit,
    )
    for ticket in tickets:
        label, key = STATUS_LABELS.get(ticket.status_category or "Open", STATUS_LABELS["Open"])
        ticket.status_label = label
        ticket.status_key = key
        ticket.updated = frappe.utils.pretty_date(ticket.modified)
    return tickets
