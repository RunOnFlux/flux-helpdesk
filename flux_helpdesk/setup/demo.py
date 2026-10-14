"""Demo data for a local or staging desk. Never run it on production.

    bench --site helpdesk.localhost execute flux_helpdesk.setup.demo.seed

Every person, ticket and answer here is made up.
"""

import frappe

CUSTOMER = "alex.rivera@example.com"

ARTICLES = [
    ("Set up a FluxNode, step by step", "FluxNodes"),
    ("Deploy your first app on FluxCloud", "FluxCloud"),
    ("Renew or upgrade a game server", "Flux Games"),
    ("Back up SSP Wallet and SSP Key", "Wallets"),
    ("Restore a ZelCore account", "Wallets"),
]

TICKETS = [
    {
        "subject": "Palworld server stuck on “starting” after renewal",
        "product": "Flux Games",
        "priority": "High",
        "message": "Hi, I renewed my Palworld server about an hour ago and it has been stuck on "
        "“starting” ever since. My friends can't join. Is my world save still there?",
        "reply": "Hi Alex, thanks for renewing. Your world save is safe. After a renewal the "
        "server starts on a fresh node and loads your world first, which takes a few minutes. "
        "If it still says “starting” in 15 minutes, just reply here.",
        "note": "Checked live: renewal paid, 2 of 3 instances running, the third is still loading "
        "the world save on a new node.",
    },
    {
        "subject": "FluxNode not confirming after an IP change",
        "product": "FluxNodes",
        "priority": "Medium",
        "message": "My ISP changed my IP last night and now my node shows as not confirmed. "
        "What do I need to update?",
    },
    {
        "subject": "Moving my app to a bigger FluxCloud plan",
        "product": "FluxCloud",
        "priority": "Low",
        "message": "Can I give my app more RAM without redeploying it?",
        "reply": "Yes. Open the app in FluxCloud, choose Update, raise the RAM and confirm. "
        "Your app keeps running while the new spec rolls out.",
        "resolve": True,
    },
]


def seed():
    if not frappe.conf.developer_mode and not frappe.conf.allow_demo_data:
        frappe.throw("Demo data is only for developer sites (developer_mode or allow_demo_data).")

    _agent("Administrator")
    _customer_user()
    _articles()
    for spec in TICKETS:
        _ticket(spec)
    frappe.db.commit()
    print("Demo data ready.")


def _agent(user: str):
    if not frappe.db.exists("HD Agent", user):
        frappe.get_doc({"doctype": "HD Agent", "user": user, "agent_name": "Flux Support"}).insert(
            ignore_permissions=True
        )


def _customer_user():
    if frappe.db.exists("User", CUSTOMER):
        return
    password = frappe.generate_hash(length=16)
    frappe.get_doc(
        {
            "doctype": "User",
            "email": CUSTOMER,
            "first_name": "Alex",
            "last_name": "Rivera",
            "user_type": "Website User",
            "send_welcome_email": 0,
            "new_password": password,
        }
    ).insert(ignore_permissions=True)
    print(f"Demo customer login: {CUSTOMER} / {password}")


def _articles():
    categories = {}
    for title, category in ARTICLES:
        if frappe.db.exists("HD Article", {"title": title}):
            continue
        if category not in categories:
            categories[category] = frappe.db.get_value(
                "HD Article Category", {"category_name": category}
            ) or (
                frappe.get_doc({"doctype": "HD Article Category", "category_name": category})
                .insert(ignore_permissions=True)
                .name
            )
        frappe.get_doc(
            {
                "doctype": "HD Article",
                "title": title,
                "category": categories[category],
                "content": f"<p>{title}. Placeholder text for the demo desk.</p>",
                "status": "Published",
            }
        ).insert(ignore_permissions=True)


def _ticket(spec: dict):
    if frappe.db.exists("HD Ticket", {"subject": spec["subject"]}):
        return
    ticket = frappe.get_doc(
        {
            "doctype": "HD Ticket",
            "subject": spec["subject"],
            "raised_by": CUSTOMER,
            "description": f"<p>{spec['message']}</p>",
            "priority": spec["priority"],
            "flux_product": spec["product"],
        }
    ).insert(ignore_permissions=True)
    # Helpdesk records the description as sent by whoever created the ticket; here, the customer.
    frappe.db.set_value(
        "Communication",
        {"reference_doctype": "HD Ticket", "reference_name": ticket.name},
        {"sender": CUSTOMER, "sender_full_name": "Alex Rivera"},
        update_modified=False,
    )
    if spec.get("note"):
        ticket.new_comment(f"<p>{spec['note']}</p>")
    if spec.get("reply"):
        # Stored as a sent reply without emailing anyone, so no mail account is needed.
        frappe.get_doc(
            {
                "doctype": "Communication",
                "communication_type": "Communication",
                "communication_medium": "Email",
                "sent_or_received": "Sent",
                "subject": f"Re: {spec['subject']}",
                "content": f"<p>{spec['reply']}</p>",
                "sender": "Administrator",
                "recipients": CUSTOMER,
                "reference_doctype": "HD Ticket",
                "reference_name": ticket.name,
                "status": "Linked",
            }
        ).insert(ignore_permissions=True)
    if spec.get("resolve"):
        ticket.reload()
        ticket.status = "Resolved"
        ticket.save(ignore_permissions=True)
