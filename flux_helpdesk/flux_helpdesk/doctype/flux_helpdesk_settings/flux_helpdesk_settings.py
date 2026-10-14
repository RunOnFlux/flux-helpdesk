import frappe
from frappe import _
from frappe.model.document import Document

DISCORD_WEBHOOK_PREFIXES = (
    "https://discord.com/api/webhooks/",
    "https://discordapp.com/api/webhooks/",
    "https://ptb.discord.com/api/webhooks/",
    "https://canary.discord.com/api/webhooks/",
)


class FluxHelpdeskSettings(Document):
    def validate(self):
        if self.knowledge_bot_url:
            self.knowledge_bot_url = self.knowledge_bot_url.strip().rstrip("/")
            if not self.knowledge_bot_url.startswith("https://"):
                frappe.throw(_("The knowledge bot URL must start with https://"))

        for field in ("discord_guild_id", "discord_role_id"):
            value = (self.get(field) or "").strip()
            if value and not value.isdigit():
                frappe.throw(_("{0} must be a number.").format(self.meta.get_label(field)))
            self.set(field, value)

        # A Password field reads back as asterisks until it changes, so only a
        # newly typed webhook can be checked.
        webhook = self.discord_webhook_url or ""
        if webhook and set(webhook) != {"*"} and not webhook.startswith(DISCORD_WEBHOOK_PREFIXES):
            frappe.throw(_("That does not look like a Discord webhook URL."))

        if self.discord_enabled and not self.discord_webhook_url:
            frappe.throw(_("Add the webhook URL before turning Discord on."))
