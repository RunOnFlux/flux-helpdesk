"""Runs the Freshdesk importer against a fake Freshdesk, inside a bench.

bench --site test.localhost run-tests --module flux_helpdesk.tests.test_importer_bench
"""

import frappe

try:
    from frappe.tests import IntegrationTestCase as TestCase
except ImportError:  # Frappe 15
    from frappe.tests.utils import FrappeTestCase as TestCase

from flux_helpdesk.importer.freshdesk import Importer, importing

TICKET_ID = 91234


class FakeFreshdesk:
    calls = 0

    def tickets(self, updated_since=None):
        return iter(
            [
                {
                    "id": TICKET_ID,
                    "subject": "Imported: node not confirming",
                    "description": "<p>My node stopped confirming after the IP change.</p>",
                    "status": 4,
                    "priority": 3,
                    "type": "Question",
                    "group_id": 7,
                    "requester_id": 501,
                    "company_id": 601,
                    "responder_id": 701,
                    "tags": ["fluxnode", "imported"],
                    "created_at": "2024-03-01T10:00:00Z",
                    "updated_at": "2024-03-02T12:00:00Z",
                    "stats": {
                        "first_responded_at": "2024-03-01T11:00:00Z",
                        "resolved_at": "2024-03-02T12:00:00Z",
                    },
                }
            ]
        )

    def ticket(self, ticket_id):
        return None

    def conversations(self, ticket_id):
        return iter(
            [
                {
                    "id": 8801,
                    "incoming": False,
                    "private": False,
                    "user_id": 701,
                    "body": "<p>Please update the IP in your node config.</p>",
                    "from_email": "Flux Support <support@example.com>",
                    "to_emails": ["importer.test@example.com"],
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
                    "from_email": "importer.test@example.com",
                    "created_at": "2024-03-02T09:00:00Z",
                },
            ]
        )

    def contact(self, contact_id):
        return {
            "id": contact_id,
            "name": "Importer Test",
            "email": "importer.test@example.com",
            "company_id": 601,
        }

    def company(self, company_id):
        return {"id": company_id, "name": "Importer Test Co", "domains": ["example.com"]}

    def agents(self):
        return iter([{"id": 701, "contact": {"email": "former.agent@example.com", "name": "Former Agent"}}])

    def groups(self):
        return iter([{"id": 7, "name": "Importer Test Team"}])

    def solution_categories(self):
        return [{"id": 1, "name": "Nodes", "description": ""}]

    def solution_folders(self, category_id):
        return [{"id": 11, "name": "Setup"}]

    def solution_articles(self, folder_id):
        return iter([{"id": 111, "title": "Imported article", "description": "<p>Body</p>", "status": 2}])


class TestFreshdeskImporter(TestCase):
    def test_full_ticket_import_is_faithful_and_idempotent(self):
        importer = Importer(FakeFreshdesk(), attachments=False)
        with importing():
            importer.import_articles()
            importer.import_tickets()

        name = "91234"
        ticket = frappe.get_doc("HD Ticket", name)
        self.assertEqual(ticket.freshdesk_id, TICKET_ID)
        self.assertEqual(ticket.status, "Resolved")
        self.assertEqual(ticket.priority, "High")
        self.assertEqual(ticket.agent_group, "Importer Test Team")
        self.assertEqual(ticket.raised_by, "importer.test@example.com")
        self.assertEqual(str(ticket.creation)[:10], "2024-03-01")
        self.assertIn("fluxnode", ticket.get_tags())

        messages = frappe.get_all(
            "Communication",
            filters={"reference_doctype": "HD Ticket", "reference_name": name},
            fields=["sender", "sent_or_received"],
            order_by="communication_date asc",
        )
        self.assertEqual([m.sent_or_received for m in messages], ["Received", "Sent", "Received"])
        self.assertEqual(messages[0].sender, "importer.test@example.com")
        self.assertEqual(messages[1].sender, "support@example.com")

        notes = frappe.get_all("HD Ticket Comment", filters={"reference_ticket": name}, pluck="content")
        self.assertEqual(len(notes), 1)
        self.assertIn("Former Agent", notes[0])

        self.assertTrue(frappe.db.exists("HD Article", {"freshdesk_id": 111}))
        series = frappe.db.sql("select current from `tabSeries` where name = ''")[0][0]
        self.assertGreaterEqual(int(series), TICKET_ID)

        # Second run: nothing new.
        again = Importer(FakeFreshdesk())
        with importing():
            again.import_articles()
            again.import_tickets()
        self.assertEqual(again.counts["tickets"], 0)
        self.assertEqual(again.counts["tickets_skipped"], 1)
        self.assertEqual(
            frappe.db.count("Communication", {"reference_doctype": "HD Ticket", "reference_name": name}), 3
        )

    def test_assignment_rules_are_restored(self):
        rules = frappe.get_all(
            "Assignment Rule", filters={"document_type": "HD Ticket", "disabled": 0}, pluck="name"
        )
        with importing():
            for rule in rules:
                self.assertEqual(frappe.db.get_value("Assignment Rule", rule, "disabled"), 1)
        for rule in rules:
            self.assertEqual(frappe.db.get_value("Assignment Rule", rule, "disabled"), 0)
