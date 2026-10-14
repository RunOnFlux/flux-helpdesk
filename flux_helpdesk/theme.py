"""Flux theme for Helpdesk's single-page app.

Helpdesk serves its agent and customer app from one HTML page at /helpdesk and
offers no hook for extra CSS. Frappe's after_request hook lets us add our
stylesheet to that page on the way out, so Helpdesk's code stays untouched and
upgrades keep working. All the actual styling lives in
public/css/flux-theme.css and only overrides frappe-ui's design tokens.
"""

import frappe

from flux_helpdesk import __version__

MARKER = "data-flux-theme"
THEME_CSS = "/assets/flux_helpdesk/css/flux-theme.css"

# frappe-ui keeps the chosen theme in localStorage["theme"] and Helpdesk writes
# "light" when nothing is stored. Writing "dark" first makes dark the default
# without overriding anyone's choice.
DARK_DEFAULT_SCRIPT = (
    "<script " + MARKER + '>try{if(!localStorage.getItem("theme"))'
    'localStorage.setItem("theme","dark")}catch(e){}</script>'
)


def is_helpdesk_page(path: str) -> bool:
    return path == "/helpdesk" or path.startswith("/helpdesk/")


def add_theme_tags(html: str, default_dark: bool, version: str = __version__) -> str:
    """Return html with the theme added to <head>; unchanged when it cannot or need not be."""
    if MARKER in html:
        return html
    head_end = html.find("</head>")
    if head_end == -1:
        return html
    tags = f'<link {MARKER} rel="stylesheet" href="{THEME_CSS}?v={version}">'
    if default_dark:
        tags += DARK_DEFAULT_SCRIPT
    return html[:head_end] + tags + html[head_end:]


def inject_theme(response, request):
    try:
        if not is_helpdesk_page(request.path or ""):
            return
        if response.status_code != 200 or response.direct_passthrough:
            return
        if response.mimetype != "text/html":
            return

        settings = frappe.get_cached_doc("Flux Helpdesk Settings")
        if not settings.theme_enabled:
            return

        html = response.get_data(as_text=True)
        themed = add_theme_tags(html, default_dark=bool(settings.default_dark))
        if themed is not html:
            response.set_data(themed)
    except Exception:
        # A theme must never take the helpdesk down.
        frappe.logger("flux_helpdesk").exception("theme injection failed")
