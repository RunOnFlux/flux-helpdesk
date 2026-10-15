"""Applied on install and on every migrate, so it must be safe to run again."""

import os

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from flux_helpdesk.utils import DEFAULT_PRODUCTS, parse_products

FORM_SCRIPT_NAME = "Flux: Ask Flux AI"
BRAND_NAME = "Flux Support"
BRAND_ICON = "/assets/flux_helpdesk/images/flux-icon.svg"


def after_install():
    apply()
    set_once_defaults()


def after_migrate():
    apply()


def apply():
    create_custom_fields(custom_fields(), update=True)
    add_fields_to_ticket_template()
    install_form_script()
    frappe.clear_cache(doctype="HD Ticket")


def product_options() -> str:
    """Every product a ticket can carry: the defaults, the support page's list, and any in use.

    Values already on tickets stay valid even after they are taken off the support page.
    """
    configured = []
    in_use = []
    if frappe.db.exists("DocType", "Flux Helpdesk Settings"):
        configured = parse_products(frappe.db.get_single_value("Flux Helpdesk Settings", "support_products"))
    if frappe.db.has_column("HD Ticket", "flux_product"):
        in_use = frappe.db.sql_list(
            "select distinct flux_product from `tabHD Ticket` where ifnull(flux_product, '') != ''"
        )
    products = dict.fromkeys([*DEFAULT_PRODUCTS, *configured, "eckoWALLET", *in_use, "Other"])
    return "\n" + "\n".join(products)


def sync_product_options():
    """Called when the product list in Flux Helpdesk Settings changes."""
    field = frappe.db.get_value("Custom Field", {"dt": "HD Ticket", "fieldname": "flux_product"})
    if field:
        frappe.db.set_value("Custom Field", field, "options", product_options())
        frappe.clear_cache(doctype="HD Ticket")


def freshdesk_id_field(insert_after: str) -> dict:
    return {
        "fieldname": "freshdesk_id",
        "label": "Freshdesk ID",
        "fieldtype": "Int",
        "insert_after": insert_after,
        "read_only": 1,
        "no_copy": 1,
        "search_index": 1,
        "hidden": 1,
    }


def custom_fields() -> dict:
    return {
        "HD Ticket": [
            {
                "fieldname": "flux_product",
                "label": "Product",
                "fieldtype": "Select",
                "options": product_options(),
                "insert_after": "ticket_type",
                "in_standard_filter": 1,
            },
            {
                "fieldname": "flux_app_name",
                "label": "App or node",
                "fieldtype": "Data",
                "insert_after": "flux_product",
                "description": "App name, node IP or wallet address the ticket is about.",
            },
            {
                "fieldname": "flux_discord_url",
                "label": "Discord message",
                "fieldtype": "Data",
                "options": "URL",
                "insert_after": "flux_app_name",
                "read_only": 1,
                "no_copy": 1,
            },
            freshdesk_id_field("flux_discord_url"),
        ],
        "Communication": [freshdesk_id_field("reference_name")],
        "Comment": [freshdesk_id_field("reference_name")],
        "Contact": [freshdesk_id_field("email_id")],
        "HD Customer": [freshdesk_id_field("domain")],
        "HD Article": [freshdesk_id_field("category")],
        "HD Article Category": [freshdesk_id_field("category_name")],
    }


def add_fields_to_ticket_template():
    """Show Product and App or node in the ticket sidebar and the customer's new-ticket form."""
    if not frappe.db.exists("HD Ticket Template", "Default"):
        return
    template = frappe.get_doc("HD Ticket Template", "Default")
    present = {row.fieldname for row in template.fields}
    changed = False
    for fieldname, placeholder in (
        ("flux_product", "Which product is this about?"),
        ("flux_app_name", "App name, node IP or wallet address"),
    ):
        if fieldname not in present:
            template.append("fields", {"fieldname": fieldname, "placeholder": placeholder})
            changed = True
    if changed:
        template.save(ignore_permissions=True)


def install_form_script():
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "form_scripts", "ask_flux_ai.js")
    with open(path) as f:
        script = f.read()

    if frappe.db.exists("HD Form Script", FORM_SCRIPT_NAME):
        doc = frappe.get_doc("HD Form Script", FORM_SCRIPT_NAME)
        if doc.script == script:
            return
        doc.script = script
        doc.save(ignore_permissions=True)
        return

    frappe.get_doc(
        {
            "doctype": "HD Form Script",
            "name": FORM_SCRIPT_NAME,
            "dt": "HD Ticket",
            "apply_to": "Form",
            "enabled": 1,
            "apply_to_customer_portal": 0,
            "script": script,
        }
    ).insert(ignore_permissions=True, set_name=FORM_SCRIPT_NAME)


def set_once_defaults():
    """Branding and the home page. Set only on install, so later edits in the UI stick."""
    hd = frappe.get_single("HD Settings")
    if not hd.brand_name or hd.brand_name == "Helpdesk":
        hd.brand_name = BRAND_NAME
    hd.brand_logo = hd.brand_logo or BRAND_ICON
    hd.favicon = hd.favicon or BRAND_ICON
    hd.save(ignore_permissions=True)

    website = frappe.get_single("Website Settings")
    if not website.home_page:
        website.home_page = "support"
        website.save(ignore_permissions=True)
