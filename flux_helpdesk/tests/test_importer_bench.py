"""Runs the Freshdesk importer against a fake Freshdesk, inside a bench.

bench --site test.localhost run-tests --module flux_helpdesk.tests.test_importer_bench
"""

import frappe
from frappe.utils import now_datetime

try:
    from frappe.tests import IntegrationTestCase as TestCase
except ImportError:  # Frappe 15
    from frappe.tests.utils import FrappeTestCase as TestCase

from flux_helpdesk.importer.freshdesk import Importer, importing

TICKET_ID = 91234  # resolved, with a reply, a note and a customer answer
OPEN_ID = 91235  # still open, assigned to an agent who exists on the new desk
OPEN_AGENT = "open.agent@example.com"
CUSTOMER = "importer.test@example.com"


class FakeFreshdesk:
    calls = 0

    def __init__(self, topped_up: bool = False):
        # topped_up: the state a few days later, after the customer wrote back on TICKET_ID.
        self.topped_up = topped_up

    def tickets(self, updated_since=None):
        return iter(
            [
                {
                    "id": TICKET_ID,
                    "subject": "Imported: node not confirming",
                    "description": "<p>My node stopped confirming after the IP change.</p>",
                    "status": 2 if self.topped_up else 4,
                    "priority": 3,
                    "type": "Question",
                    "group_id": 7,
                    "requester_id": 501,
                    "company_id": 601,
                    "responder_id": 701,
                    "tags": ["fluxnode", "imported"] + (["reopened"] if self.topped_up else []),
                    "created_at": "2024-03-01T10:00:00Z",
                    "updated_at": "2024-03-05T08:00:00Z" if self.topped_up else "2024-03-02T12:00:00Z",
                    "stats": {
                        "first_responded_at": "2024-03-01T11:00:00Z",
                        "resolved_at": None if self.topped_up else "2024-03-02T12:00:00Z",
                    },
                },
                {
                    "id": OPEN_ID,
                    "subject": "Imported: still waiting on us",
                    "description": "<p>Any update?</p>",
                    "status": 2,
                    "priority": 2,
                    "requester_id": 501,
                    "responder_id": 702,
                    "created_at": "2024-03-04T10:00:00Z",
                    "updated_at": "2024-03-04T10:00:00Z",
                    "stats": {},
                },
            ]
        )

    def newest_ticket_id(self):
        return OPEN_ID

    def ticket(self, ticket_id):
        return None

    def conversations(self, ticket_id):
        if ticket_id == OPEN_ID:
            return iter([])
        rows = [
            {
                "id": 8801,
                "incoming": False,
                "private": False,
                "user_id": 701,
                "body": "<p>Please update the IP in your node config.</p>",
                "from_email": "Flux Support <support@example.com>",
                "to_emails": [CUSTOMER],
                "created_at": "2024-03-01T11:00:00Z",
            },
            {
                "id": 8802,
                "incoming": False,
                "private": True,
                "user_id": 701,
                "body": "<p>Customer runs two nodes.</p>",
                "created_at": "2024-03-01T11:05:00Z",
            },
            {
                "id": 8803,
                "incoming": True,
                "private": False,
                "user_id": 501,
                "body": "<p>Done, thanks!</p>",
                "from_email": CUSTOMER,
                "created_at": "2024-03-02T09:00:00Z",
            },
        ]
        if self.topped_up:
            rows.append(
                {
                    "id": 8804,
                    "incoming": True,
                    "private": False,
                    "user_id": 501,
                    "body": "<p>It stopped again.</p>",
                    "from_email": CUSTOMER,
                    "created_at": "2024-03-05T08:00:00Z",
                }
            )
        return iter(rows)

    def contact(self, contact_id):
        return {"id": contact_id, "name": "Importer Test", "email": CUSTOMER, "company_id": 601}

    def company(self, company_id):
        return {"id": company_id, "name": "Importer Test Co", "domains": ["example.com"]}

    def agents(self):
        return iter(
            [
                {"id": 701, "contact": {"email": "former.agent@example.com", "name": "Former Agent"}},
                {"id": 702, "contact": {"email": OPEN_AGENT, "name": "Open Agent"}},
            ]
        )

    def groups(self):
        return iter([{"id": 7, "name": "Importer Test Team"}])

    def solution_categories(self):
        return [{"id": 1, "name": "Nodes", "description": ""}]

    def solution_folders(self, category_id):
        return [
            {"id": 11, "name": "Setup", "visibility": 1},
            {"id": 12, "name": "Internal runbooks", "visibility": 3},
        ]

    def solution_articles(self, folder_id):
        if folder_id == 12:
            return iter([{"id": 112, "title": "Imported runbook", "description": "<p>x</p>", "status": 2}])
        return iter([{"id": 111, "title": "Imported article", "description": "<p>Body</p>", "status": 2}])


def _remove_earlier_runs():
    for name in frappe.get_all("HD Ticket", {"freshdesk_id": ["in", [TICKET_ID, OPEN_ID]]}, pluck="name"):
        frappe.delete_doc("HD Ticket", name, force=True, ignore_permissions=True)
    for doctype, ids in (
        ("Communication", [8801, 8803, 8804]),
        ("Comment", [8802]),
        ("HD Article", [111, 112]),
        ("HD Article Category", [11, 12]),
    ):
        frappe.db.delete(doctype, {"freshdesk_id": ["in", ids]})
    frappe.db.commit()


def _ensure_agent(email: str):
    if not frappe.db.exists("User", email):
        frappe.get_doc(
            {"doctype": "User", "email": email, "first_name": "Open", "send_welcome_email": 0}
        ).insert(ignore_permissions=True)
    if not frappe.db.exists("HD Agent", email):
        frappe.get_doc({"doctype": "HD Agent", "user": email, "agent_name": "Open Agent"}).insert(
            ignore_permissions=True
        )
    frappe.db.commit()


class TestFreshdeskImporter(TestCase):
    def setUp(self):
        _remove_earlier_runs()
        _ensure_agent(OPEN_AGENT)

    def test_full_ticket_import_is_faithful_and_idempotent(self):
        started = now_datetime()
        importer = Importer(FakeFreshdesk(), attachments=False)
        with importing():
            importer.import_articles()
            importer.import_tickets()
        if importer.counts["errors"]:
            self.fail(frappe.get_last_doc("Error Log").error)

        name = str(TICKET_ID)
        ticket = frappe.get_doc("HD Ticket", name)
        self.assertEqual(ticket.freshdesk_id, TICKET_ID)
        self.assertEqual(ticket.status, "Resolved")
        self.assertEqual(ticket.priority, "High")
        self.assertEqual(ticket.agent_group, "Importer Test Team")
        self.assertEqual(ticket.raised_by, CUSTOMER)
        self.assertEqual(str(ticket.creation)[:10], "2024-03-01")
        self.assertIn("fluxnode", ticket.get_tags())

        messages = frappe.get_all(
            "Communication",
            filters={"reference_doctype": "HD Ticket", "reference_name": name},
            fields=["sender", "sent_or_received"],
            order_by="communication_date asc",
        )
        self.assertEqual([m.sent_or_received for m in messages], ["Received", "Sent", "Received"])
        self.assertEqual(messages[0].sender, CUSTOMER)
        # Agent replies show the agent who answered, not the shared mailbox.
        self.assertEqual(messages[1].sender, "former.agent@example.com")

        notes = frappe.get_all(
            "Comment",
            filters={"reference_doctype": "HD Ticket", "reference_name": name, "comment_type": "Comment"},
            pluck="content",
        )
        self.assertEqual(len(notes), 1)
        self.assertIn("Former Agent", notes[0])

        # The open ticket is assigned to its Freshdesk agent, who exists here.
        self.assertIn(
            OPEN_AGENT, frappe.parse_json(frappe.db.get_value("HD Ticket", str(OPEN_ID), "_assign"))
        )

        # Agents-only Freshdesk folders do not become public articles.
        self.assertEqual(frappe.db.get_value("HD Article", {"freshdesk_id": 111}, "status"), "Published")
        self.assertEqual(frappe.db.get_value("HD Article", {"freshdesk_id": 112}, "status"), "Draft")

        series = frappe.db.sql("select current from `tabSeries` where name = ''")[0][0]
        self.assertGreaterEqual(int(series), OPEN_ID)

        # Nothing the import did is waiting to be emailed once the site is unmuted.
        self.assertEqual(
            frappe.db.count("Email Queue", {"status": "Not Sent", "creation": [">=", started]}), 0
        )

        # Second run: nothing new.
        again = Importer(FakeFreshdesk())
        with importing():
            again.import_articles()
            again.import_tickets()
        self.assertEqual(again.counts["tickets"], 0)
        self.assertEqual(again.counts["tickets_skipped"], 2)
        self.assertEqual(
            frappe.db.count("Communication", {"reference_doctype": "HD Ticket", "reference_name": name}), 3
        )

    def test_top_up_brings_imported_tickets_up_to_date(self):
        with importing():
            Importer(FakeFreshdesk()).import_tickets()

        later = Importer(FakeFreshdesk(topped_up=True))
        with importing():
            later.import_tickets(since="2024-03-03T00:00:00Z")
        self.assertEqual(later.counts["errors"], 0)
        self.assertEqual(later.counts["tickets_refreshed"], 2)
        self.assertEqual(later.counts["replies"], 1)

        name = str(TICKET_ID)
        self.assertEqual(frappe.db.get_value("HD Ticket", name, "status"), "Open")
        self.assertEqual(
            frappe.db.count("Communication", {"reference_doctype": "HD Ticket", "reference_name": name}), 4
        )
        self.assertIn("reopened", frappe.get_doc("HD Ticket", name).get_tags())

    def test_assignment_rules_are_restored(self):
        rules = frappe.get_all(
            "Assignment Rule", filters={"document_type": "HD Ticket", "disabled": 0}, pluck="name"
        )
        with importing():
            for rule in rules:
                self.assertEqual(frappe.db.get_value("Assignment Rule", rule, "disabled"), 1)
        for rule in rules:
            self.assertEqual(frappe.db.get_value("Assignment Rule", rule, "disabled"), 0)
