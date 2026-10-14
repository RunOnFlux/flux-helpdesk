app_name = "flux_helpdesk"
app_title = "Flux Helpdesk"
app_publisher = "Flux"
app_description = "Flux theme, support page, AI answers, Discord alerts and a Freshdesk importer"
app_email = "support@runonflux.io"
app_license = "AGPL-3.0"
required_apps = ["helpdesk"]

# Install and upgrade
# -------------------
# Custom fields, the agent "Ask Flux AI" button and branding are (re)applied on
# every migrate, so an upgrade of Helpdesk never leaves them behind.
after_install = "flux_helpdesk.setup.install.after_install"
after_migrate = "flux_helpdesk.setup.install.after_migrate"

# Theme
# -----
# Helpdesk's agent and customer app at /helpdesk is a single page with no CSS
# hook. Instead of forking it, the response is given our stylesheet on the way
# out. See flux_helpdesk/theme.py.
after_request = ["flux_helpdesk.theme.inject_theme"]

# Frappe's own website pages (login, password reset) get the Flux look too.
web_include_css = ["/assets/flux_helpdesk/css/flux-web.css"]

# Discord
# -------
doc_events = {
    "HD Ticket": {
        "after_insert": "flux_helpdesk.discord.on_ticket_insert",
        "on_update": "flux_helpdesk.discord.on_ticket_update",
    },
    "Communication": {
        "after_insert": "flux_helpdesk.discord.on_communication_insert",
    },
}
