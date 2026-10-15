"""Freshdesk → Helpdesk import.

Run it inside the bench, against a site that does not send email:

    bench --site support.runonflux.io set-config mute_emails 1
    bench --site support.runonflux.io set-config freshdesk_domain yourcompany.freshdesk.com
    bench --site support.runonflux.io set-config freshdesk_api_key <key>
    bench --site support.runonflux.io execute flux_helpdesk.importer.freshdesk.run \
        --kwargs '{"limit": 50}'

What moves: help articles, groups (as teams), companies, contacts, tickets with
their original numbers, every public reply and private note, tags, and
optionally attachments. Each imported record remembers its Freshdesk ID, so
running it again skips what is already there and picks up where it stopped.
With `since`, tickets that were already imported are brought up to date too.

Side effects are switched off while it runs: no emails, no assignment rules,
no Discord posts. See docs/freshdesk-import.md.
"""

import os
from contextlib import contextmanager

import frappe
from frappe.cache_manager import clear_doctype_map
from frappe.utils import get_system_timezone, now_datetime

from flux_helpdesk.importer import mapping
from flux_helpdesk.importer.client import FreshdeskClient

MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024


def run(
    limit: int | None = None,
    since: str | None = None,
    tickets: bool = True,
    articles: bool = True,
    attachments: bool = False,
    assign_open: bool = True,
    dry_run: bool = False,
    allow_email: bool = False,
):
    """Entry point for `bench execute`. Arguments are documented in docs/freshdesk-import.md."""
    if not allow_email and not frappe.are_emails_muted():
        frappe.throw(
            "Emails are not muted on this site. Run `bench --site <site> set-config mute_emails 1` "
            "first, or pass allow_email=True if you really mean it."
        )

    domain = frappe.conf.get("freshdesk_domain") or os.environ.get("FRESHDESK_DOMAIN")
    api_key = frappe.conf.get("freshdesk_api_key") or os.environ.get("FRESHDESK_API_KEY")
    if not (domain and api_key):
        frappe.throw("Set freshdesk_domain and freshdesk_api_key in site config (or the environment).")

    importer = Importer(FreshdeskClient(domain, api_key), attachments=attachments, assign_open=assign_open)
    with importing(purge_queued_email=not allow_email):
        if articles:
            importer.import_articles(dry_run=dry_run)
        if tickets:
            importer.import_tickets(limit=limit, since=since, dry_run=dry_run)
    importer.report()
    return importer.counts


@contextmanager
def importing(purge_queued_email: bool = True):
    """Silence everything that should not fire for history: email, assignment, alerts."""
    flags = ("mute_emails", "in_import", "initial_sync", "flux_importing")
    saved = {flag: frappe.flags.get(flag) for flag in flags}
    for flag in flags:
        frappe.flags[flag] = True
    started = now_datetime()

    rules = frappe.get_all(
        "Assignment Rule", filters={"document_type": "HD Ticket", "disabled": 0}, pluck="name"
    )
    _set_rules_disabled(rules, 1)
    try:
        yield
    finally:
        _set_rules_disabled(rules, 0)
        if purge_queued_email:
            _purge_email_queued_since(started)
        for flag, value in saved.items():
            frappe.flags[flag] = value


def _set_rules_disabled(rules: list[str], disabled: int):
    for rule in rules:
        frappe.db.set_value("Assignment Rule", rule, "disabled", disabled, update_modified=False)
    frappe.db.commit()
    # Assignment rules are read from a cached list, which db.set_value does not clear.
    clear_doctype_map("Assignment Rule", "HD Ticket")


def _purge_email_queued_since(started):
    """Muted email still lands in the Email Queue and goes out once the site is unmuted.

    Nothing the import queues is meant for anyone, so drop it before that can happen.
    """
    queued = frappe.get_all(
        "Email Queue", filters={"status": "Not Sent", "creation": [">=", started]}, pluck="name"
    )
    if queued:
        frappe.db.delete("Email Queue Recipient", {"parent": ["in", queued]})
        frappe.db.delete("Email Queue", {"name": ["in", queued]})
        frappe.db.commit()
        print(f"Removed {len(queued)} emails the import had queued.")


class Importer:
    def __init__(self, client: FreshdeskClient, attachments: bool = False, assign_open: bool = True):
        self.client = client
        self.attachments = attachments
        self.assign_open = assign_open
        self.tz = _site_tz()
        self.counts = {
            "tickets": 0,
            "tickets_skipped": 0,
            "tickets_refreshed": 0,
            "replies": 0,
            "notes": 0,
            "contacts": 0,
            "companies": 0,
            "teams": 0,
            "articles": 0,
            "attachments": 0,
            "errors": 0,
        }
        self._contacts: dict[int, tuple[str, str]] = {}
        self._companies: dict[int, str | None] = {}
        self._agents: dict[int, dict] | None = None
        self._groups: dict[int, str] | None = None
        self._statuses = set(frappe.get_all("HD Ticket Status", pluck="name"))

    # Help articles --------------------------------------------------------

    def import_articles(self, dry_run: bool = False):
        for category in self.client.solution_categories():
            folders = self.client.solution_folders(category["id"])
            for folder in folders:
                name = folder["name"] if len(folders) > 1 else category["name"]
                category_name = None if dry_run else self._article_category(folder["id"], name, category)
                for article in self.client.solution_articles(folder["id"]):
                    if dry_run:
                        self.counts["articles"] += 1
                        continue
                    if frappe.db.exists("HD Article", {"freshdesk_id": article["id"]}):
                        continue
                    doc = frappe.get_doc(
                        {
                            "doctype": "HD Article",
                            "title": article["title"][:140],
                            "content": article.get("description") or "",
                            "category": category_name,
                            "status": mapping.article_status(article.get("status"), folder.get("visibility")),
                            "published_on": mapping.to_site_time(article.get("created_at"), self.tz),
                            "freshdesk_id": article["id"],
                        }
                    )
                    doc.insert(ignore_permissions=True)
                    self.counts["articles"] += 1
                frappe.db.commit()

    def _article_category(self, folder_id: int, name: str, category: dict) -> str:
        existing = frappe.db.get_value("HD Article Category", {"freshdesk_id": folder_id})
        if existing:
            return existing
        doc = frappe.get_doc(
            {
                "doctype": "HD Article Category",
                "category_name": name[:140],
                "description": category.get("description") or "",
                "freshdesk_id": folder_id,
            }
        ).insert(ignore_permissions=True)
        return doc.name

    # Tickets --------------------------------------------------------------

    def import_tickets(self, limit: int | None = None, since: str | None = None, dry_run: bool = False):
        if not dry_run:
            self._reserve_numbers()
        # A top-up (`since`) also brings already imported tickets up to date. A plain re-run
        # skips them, so resuming a full import does not re-read every conversation.
        refresh = bool(since)
        seen = 0
        for summary in self.client.tickets(updated_since=since or "2000-01-01T00:00:00Z"):
            if limit and seen >= limit:
                break
            seen += 1
            if dry_run:
                self.counts["tickets"] += 1
                continue
            existing = frappe.db.get_value("HD Ticket", {"freshdesk_id": summary["id"]})
            if existing and not refresh:
                self.counts["tickets_skipped"] += 1
                continue
            try:
                if existing:
                    self.refresh_ticket(existing, summary)
                else:
                    self.import_ticket(summary)
                frappe.db.commit()
            except Exception:
                frappe.db.rollback()
                # Contacts and companies created in the rolled-back ticket are gone too.
                self._contacts.clear()
                self._companies.clear()
                self.counts["errors"] += 1
                frappe.log_error(title=f"Freshdesk import: ticket {summary['id']}")
            if seen % 50 == 0:
                print(
                    f"… {seen} tickets read, {self.counts['tickets']} imported, {self.client.calls} API calls"
                )

    def _reserve_numbers(self):
        """Keep every Freshdesk number free for its own ticket.

        Helpdesk names tickets from the ".####" series (empty prefix). Moving it past the
        newest Freshdesk number before importing means a ticket opened on the new desk
        meanwhile cannot take a number an imported ticket needs. Helpdesk's sample
        "Welcome to Helpdesk" ticket holds 0001, so it goes.
        """
        welcome = frappe.db.get_value(
            "HD Ticket",
            {"subject": "Welcome to Helpdesk", "raised_by": "john@example.com"},
            ["name", "freshdesk_id"],
            as_dict=True,
        )
        if welcome and not welcome.freshdesk_id:
            frappe.delete_doc("HD Ticket", welcome.name, ignore_permissions=True, force=True)
            print(f"Removed Helpdesk's sample ticket {welcome.name}.")
        newest = self.client.newest_ticket_id()
        if newest:
            frappe.db.sql(
                """insert into `tabSeries` (name, current) values ('', %(n)s)
                   on duplicate key update current = greatest(current, %(n)s)""",
                {"n": newest},
            )
        frappe.db.commit()

    def import_ticket(self, ticket: dict):
        if "description" not in ticket:
            ticket = self.client.ticket(ticket["id"]) or ticket
        name = mapping.ticket_name(ticket["id"])
        if frappe.db.exists("HD Ticket", name):
            raise frappe.ValidationError(
                f"Ticket number {name} is already taken by a ticket not from Freshdesk"
            )

        email, contact = self._contact(ticket.get("requester_id"))
        status = self._status(ticket)

        doc = frappe.get_doc(
            {
                "doctype": "HD Ticket",
                "subject": (ticket.get("subject") or "(no subject)")[:140],
                "raised_by": email,
                "contact": contact,
                "description": ticket.get("description") or ticket.get("description_text") or "",
                "priority": mapping.priority(ticket.get("priority")),
                "ticket_type": self._ticket_type(ticket.get("type")),
                "agent_group": self._team(ticket.get("group_id")),
                "customer": self._company(ticket.get("company_id")),
                "freshdesk_id": ticket["id"],
            }
        )
        doc.flags.ignore_permissions = True
        doc.flags.ignore_mandatory = True
        doc.insert(set_name=name)
        for tag in ticket.get("tags") or []:
            doc.add_tag(tag[:140])

        created = mapping.to_site_time(ticket.get("created_at"), self.tz)
        self._fix_first_message(doc.name, email, created)
        if self.attachments:
            # The ticket list leaves attachments out; only the single-ticket view has them.
            full = ticket if "attachments" in ticket else (self.client.ticket(ticket["id"]) or {})
            first = frappe.db.get_value(
                "Communication", {"reference_doctype": "HD Ticket", "reference_name": doc.name}
            )
            for attachment in full.get("attachments") or []:
                self._attach(attachment, "Communication", first, doc.name)

        first_agent, last_agent, last_customer = self._conversations(
            doc.name, doc.subject, email, ticket, created
        )
        self._finish(doc.name, ticket, status, created, first_agent, last_agent, last_customer)
        if self.assign_open and status in ("Open", "Replied"):
            self._assign(doc.name, ticket.get("responder_id"))
        self.counts["tickets"] += 1

    def refresh_ticket(self, name: str, ticket: dict):
        """Bring an imported ticket up to date: new replies and notes, status, tags."""
        doc = frappe.get_doc("HD Ticket", name)
        created = mapping.to_site_time(ticket.get("created_at"), self.tz)
        first_agent, last_agent, last_customer = self._conversations(
            name, doc.subject, doc.raised_by, ticket, created
        )
        self._finish(name, ticket, self._status(ticket), created, first_agent, last_agent, last_customer)
        present = set(doc.get_tags())
        for tag in ticket.get("tags") or []:
            if tag[:140] not in present:
                doc.add_tag(tag[:140])
        self.counts["tickets_refreshed"] += 1

    def _conversations(self, ticket: str, subject: str, email: str, source: dict, created):
        """Import the replies and notes not imported yet; return first/last response times."""
        last_customer, last_agent, first_agent = created, None, None
        for conversation in self.client.conversations(source["id"]):
            when = mapping.to_site_time(conversation.get("created_at"), self.tz)
            if conversation.get("private"):
                self._note(ticket, conversation, when)
                continue
            self._reply(ticket, subject, email, conversation, when)
            if conversation.get("incoming"):
                last_customer = when
            else:
                last_agent = when
                first_agent = first_agent or when
        return first_agent, last_agent, last_customer

    def _status(self, ticket: dict) -> str:
        status = mapping.status(ticket.get("status"))
        return status if status in self._statuses else "Open"

    def _fix_first_message(self, ticket: str, email: str, created):
        """Helpdesk turns the description into the first message, sent "now" by the importing user."""
        frappe.db.sql(
            """update `tabCommunication` set sender=%s, sender_full_name=%s, creation=%s,
               modified=%s, communication_date=%s
               where reference_doctype='HD Ticket' and reference_name=%s""",
            (email, email, created, created, created, ticket),
        )

    def _reply(self, ticket: str, subject: str, customer_email: str, conversation: dict, when):
        if frappe.db.exists("Communication", {"freshdesk_id": conversation["id"]}):
            return
        incoming = bool(conversation.get("incoming"))
        agent = self._agent(conversation.get("user_id"))
        if incoming:
            sender = conversation.get("from_email") or customer_email
        else:
            # Show which agent answered; the email itself went out from the support mailbox.
            sender = agent.get("email") or conversation.get("from_email")
        comm = frappe.new_doc("Communication")
        comm.update(
            {
                "communication_type": "Communication",
                "communication_medium": "Email",
                "sent_or_received": "Received" if incoming else "Sent",
                "subject": f"Re: {subject}",
                "content": conversation.get("body") or conversation.get("body_text") or "",
                "sender": _email_only(sender) or customer_email,
                "recipients": ", ".join(conversation.get("to_emails") or [])
                or (None if incoming else customer_email),
                "cc": ", ".join(conversation.get("cc_emails") or []) or None,
                "reference_doctype": "HD Ticket",
                "reference_name": ticket,
                "status": "Linked",
                "email_status": "Open",
                "communication_date": when,
                "freshdesk_id": conversation["id"],
            }
        )
        _insert_raw(comm, when)
        self.counts["replies"] += 1
        if self.attachments:
            for attachment in conversation.get("attachments") or []:
                self._attach(attachment, "Communication", comm.name, ticket)

    def _note(self, ticket: str, conversation: dict, when):
        if frappe.db.exists("Comment", {"freshdesk_id": conversation["id"]}):
            return
        agent = self._agent(conversation.get("user_id"))
        user = (
            agent.get("email")
            if agent.get("email") and frappe.db.exists("User", agent.get("email"))
            else "Administrator"
        )
        author = agent.get("name") or "an agent"
        body = conversation.get("body") or conversation.get("body_text") or ""
        if user == "Administrator":
            body = f"<p><em>Note by {frappe.utils.escape_html(author)} in Freshdesk</em></p>{body}"
        # Helpdesk 1.31+ keeps internal notes as core Comments on the ticket.
        note = frappe.new_doc("Comment")
        note.update(
            {
                "comment_type": "Comment",
                "reference_doctype": "HD Ticket",
                "reference_name": ticket,
                "comment_email": user,
                "comment_by": frappe.db.get_value("User", user, "full_name") or author,
                "content": body,
                "freshdesk_id": conversation["id"],
            }
        )
        _insert_raw(note, when, owner=user)
        self.counts["notes"] += 1

    def _finish(
        self, ticket: str, source: dict, status: str, created, first_agent, last_agent, last_customer
    ):
        stats = source.get("stats") or {}
        resolved = mapping.to_site_time(stats.get("resolved_at") or stats.get("closed_at"), self.tz)
        updated = mapping.to_site_time(source.get("updated_at"), self.tz) or created
        values = {
            "status": status,
            "status_category": frappe.db.get_value("HD Ticket Status", status, "category") or "Open",
            "opening_date": created.date() if created else None,
            "opening_time": created.time() if created else None,
            "first_responded_on": mapping.to_site_time(stats.get("first_responded_at"), self.tz)
            or first_agent,
            "last_agent_response": last_agent,
            "last_customer_response": last_customer,
            "resolution_date": resolved if status in ("Resolved", "Closed") else None,
        }
        if status in ("Resolved", "Closed"):
            # SLAs did not exist for history; keep reports about the new desk.
            values.update({"sla": None, "agreement_status": None, "response_by": None, "resolution_by": None})
        frappe.db.set_value("HD Ticket", ticket, values, update_modified=False)
        frappe.db.sql(
            "update `tabHD Ticket` set creation=%s, modified=%s where name=%s",
            (created, updated, ticket),
        )

    def _assign(self, ticket: str, responder_id: int | None):
        email = self._agent(responder_id).get("email")
        if not email or not frappe.db.exists("HD Agent", email):
            return
        from frappe.desk.form.assign_to import add

        # The import runs as Administrator, so the public API's permission check passes.
        add({"assign_to": [email], "doctype": "HD Ticket", "name": ticket})

    # Lookups --------------------------------------------------------------

    def _contact(self, requester_id: int | None) -> tuple[str, str | None]:
        if requester_id in self._contacts:
            return self._contacts[requester_id]
        data = self.client.contact(requester_id) if requester_id else None
        email = (data or {}).get("email") or mapping.fallback_email(requester_id)
        name = (data or {}).get("name") or email.split("@")[0]

        contact = frappe.db.get_value("Contact", {"freshdesk_id": requester_id}) if requester_id else None
        contact = contact or frappe.db.get_value("Contact Email", {"email_id": email}, "parent")
        if not contact:
            doc = frappe.get_doc(
                {
                    "doctype": "Contact",
                    "first_name": name[:140],
                    "email_ids": [{"email_id": email, "is_primary": 1}],
                    "freshdesk_id": requester_id,
                }
            )
            company = self._company((data or {}).get("company_id"))
            if company:
                doc.append("links", {"link_doctype": "HD Customer", "link_name": company})
            doc.insert(ignore_permissions=True)
            contact = doc.name
            self.counts["contacts"] += 1
        self._contacts[requester_id] = (email, contact)
        return email, contact

    def _company(self, company_id: int | None) -> str | None:
        if not company_id:
            return None
        if company_id in self._companies:
            return self._companies[company_id]
        name = frappe.db.get_value("HD Customer", {"freshdesk_id": company_id})
        if not name:
            data = self.client.company(company_id)
            if data and data.get("name"):
                name = data["name"][:140]
                if not frappe.db.exists("HD Customer", name):
                    domains = data.get("domains") or []
                    frappe.get_doc(
                        {
                            "doctype": "HD Customer",
                            "customer_name": name,
                            "domain": domains[0] if domains else None,
                            "freshdesk_id": company_id,
                        }
                    ).insert(ignore_permissions=True)
                    self.counts["companies"] += 1
        self._companies[company_id] = name
        return name

    def _agent(self, agent_id: int | None) -> dict:
        if self._agents is None:
            self._agents = {
                a["id"]: {
                    "email": (a.get("contact") or {}).get("email"),
                    "name": (a.get("contact") or {}).get("name"),
                }
                for a in self.client.agents()
            }
        return self._agents.get(agent_id) or {}

    def _team(self, group_id: int | None) -> str | None:
        if not group_id:
            return None
        if self._groups is None:
            self._groups = {g["id"]: g["name"][:140] for g in self.client.groups()}
        name = self._groups.get(group_id)
        if name and not frappe.db.exists("HD Team", name):
            # Teams arrive empty; agents are added in Helpdesk afterwards.
            frappe.get_doc({"doctype": "HD Team", "team_name": name}).insert(
                ignore_permissions=True, ignore_mandatory=True
            )
            # Each team gets a round-robin rule, which fails with nobody in it. It stays off
            # until the team is saved with agents; HD Team turns it back on then.
            rule = frappe.db.get_value("HD Team", name, "assignment_rule")
            if rule:
                frappe.db.set_value("Assignment Rule", rule, "disabled", 1, update_modified=False)
            self.counts["teams"] += 1
        return name

    def _ticket_type(self, name: str | None) -> str | None:
        if not name:
            return None
        if not frappe.db.exists("HD Ticket Type", name):
            frappe.get_doc({"doctype": "HD Ticket Type", "__newname": name}).insert(ignore_permissions=True)
        return name

    def _attach(self, attachment: dict, doctype: str, docname: str | None, ticket: str):
        if not docname or (attachment.get("size") or 0) > MAX_ATTACHMENT_BYTES:
            return
        import requests

        try:
            response = requests.get(attachment["attachment_url"], timeout=120)
            response.raise_for_status()
        except Exception:
            self.counts["errors"] += 1
            return
        for target_doctype, target in ((doctype, docname), ("HD Ticket", ticket)):
            frappe.get_doc(
                {
                    "doctype": "File",
                    "file_name": attachment.get("name") or "attachment",
                    "attached_to_doctype": target_doctype,
                    "attached_to_name": target,
                    "is_private": 1,
                    "content": response.content,
                }
            ).save(ignore_permissions=True)
        self.counts["attachments"] += 1

    def report(self):
        summary = ", ".join(f"{k}: {v}" for k, v in self.counts.items())
        print(f"Freshdesk import done. {summary}. API calls: {self.client.calls}")


def _insert_raw(doc, when, owner: str = "Administrator"):
    """Insert without hooks, so history does not reopen tickets or restart SLAs."""
    doc.set_new_name()
    doc.owner = owner
    doc.modified_by = owner
    doc.creation = when
    doc.modified = when
    doc.db_insert()


def _email_only(value: str | None) -> str | None:
    if not value:
        return None
    if "<" in value and ">" in value:
        return value.split("<", 1)[1].split(">", 1)[0].strip()
    return value.strip()


def _site_tz():
    from zoneinfo import ZoneInfo

    return ZoneInfo(get_system_timezone() or "UTC")
