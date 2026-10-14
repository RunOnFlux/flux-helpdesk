"""How Freshdesk values become Helpdesk values. Pure functions, unit tested."""

from datetime import datetime, timezone

# Freshdesk status codes: https://developers.freshdesk.com/api/#ticket_attributes
STATUS = {
    2: "Open",
    3: "Replied",  # Pending: waiting on the customer
    4: "Resolved",
    5: "Closed",
}
PRIORITY = {1: "Low", 2: "Medium", 3: "High", 4: "Urgent"}
SOURCE = {
    1: "Email",
    2: "Portal",
    3: "Phone",
    7: "Chat",
    9: "Feedback widget",
    10: "Outbound email",
}


def ticket_name(freshdesk_id: int) -> str:
    """Keep the Freshdesk number, in Helpdesk's own ".####" format (at least four digits)."""
    return f"{int(freshdesk_id):04d}"


def status(code: int | None) -> str:
    # Custom Freshdesk statuses (6 and up) have no counterpart; they stay open.
    return STATUS.get(code or 2, "Open")


def priority(code: int | None) -> str:
    return PRIORITY.get(code or 2, "Medium")


def parse_time(value: str | None) -> datetime | None:
    """Freshdesk timestamps are UTC ISO 8601 ("2026-10-13T19:44:57Z")."""
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def to_site_time(value: str | None, site_tz) -> datetime | None:
    """A naive datetime in the site's timezone, which is how Frappe stores datetimes."""
    parsed = parse_time(value)
    if parsed is None:
        return None
    return parsed.astimezone(site_tz).replace(tzinfo=None)


def article_status(code: int | None) -> str:
    return "Published" if code == 2 else "Draft"


def fallback_email(requester_id: int | None) -> str:
    """For tickets whose requester was deleted in Freshdesk."""
    return f"freshdesk-requester-{requester_id or 'unknown'}@invalid.example"
