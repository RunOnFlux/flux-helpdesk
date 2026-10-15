# Freshdesk import

Moves Freshdesk history into Helpdesk. It runs inside the bench, talks to the Freshdesk API v2, and can be run as often as needed: every record keeps its Freshdesk ID, so a plain re-run skips what is already there, and a top-up with `since` also brings imported tickets up to date (new replies and notes, status, tags).

## What comes over

| Freshdesk | Helpdesk |
|---|---|
| Solution categories, folders, articles | HD Article Category, HD Article. Published only if the article is published and its folder is visible to all users; folders for logged-in users, agents or selected companies come over as drafts, because Helpdesk has no such levels and anyone can read a published article |
| Groups | HD Team |
| Companies | HD Customer |
| Contacts (requesters) | Contact, linked to their HD Customer |
| Tickets | HD Ticket with **the same number** (e.g. #15919), subject, description, priority, type, team, tags, status, dates |
| Public replies | Email messages on the ticket, with the original dates; agent replies show the agent who answered |
| Private notes | Internal comments (by the agent if they exist in Helpdesk, otherwise marked "Note by … in Freshdesk") |
| Attachments (optional) | Private files on the message and the ticket, up to 20 MB each |

Statuses: Open → Open, Pending → Replied, Resolved → Resolved, Closed → Closed; custom statuses → Open. Closed and resolved history gets no SLA, so SLA reports describe the new desk only. Open tickets are assigned to the same agent, if that agent exists in Helpdesk.

## While it runs

- **No email.** The importer refuses to start unless `mute_emails` is set on the site.
- **No auto-assignment.** Assignment rules for HD Ticket are paused and turned back on afterwards, even if the import fails.
- **No Discord posts.**
- **Nothing left in the outbox.** Muted email still lands in the Email Queue and would go out once the site is unmuted, so anything queued during the run is removed at the end.
- **Numbers are reserved first.** Before importing, the ticket counter moves past the newest Freshdesk number, so a ticket opened on the new desk meanwhile cannot take a number an imported ticket needs. Helpdesk's sample "Welcome to Helpdesk" ticket (#0001) is deleted for the same reason.

## Run it

```bash
C="docker compose -f deploy/compose.yaml --env-file deploy/.env"
SITE=support.runonflux.io
# MUTE_EMAILS=1 must be set in deploy/.env (it is re-applied on every `up`)
$C exec backend bench --site $SITE set-config freshdesk_domain runonflux.freshdesk.com
$C exec backend bench --site $SITE set-config freshdesk_api_key '<admin API key>'

# 1. Count only, change nothing
$C exec backend bench --site $SITE execute flux_helpdesk.importer.freshdesk.run --kwargs '{"dry_run": true}'
# 2. A small real batch, then look at the tickets in /helpdesk
$C exec backend bench --site $SITE execute flux_helpdesk.importer.freshdesk.run --kwargs '{"limit": 50}'
# 3. Everything (add "attachments": true to bring files)
$C exec backend bench --site $SITE execute flux_helpdesk.importer.freshdesk.run
# 4. At cutover: what changed in Freshdesk since the full import (use its start date)
$C exec backend bench --site $SITE execute flux_helpdesk.importer.freshdesk.run --kwargs '{"since": "2026-10-16"}'

# Afterwards, remove the key from the site config
$C exec backend bench --site $SITE set-config freshdesk_api_key ''
```

Use the account domain (`runonflux.freshdesk.com`), not the portal domain; the API does not answer on the portal. The key must belong to an **admin** so every ticket and note is visible.

| Argument | Default | Meaning |
|---|---|---|
| `limit` | all | Stop after this many tickets |
| `since` | none | Only tickets updated since this ISO date, and bring those already imported up to date; use for the final top-up |
| `tickets` / `articles` | true | Skip either part |
| `attachments` | false | Download attachments (one extra API call per ticket for the opening message's files) |
| `assign_open` | true | Assign open tickets to their Freshdesk agent |
| `dry_run` | false | Count only |

## Time and rate limits

Each ticket costs about two API calls (ticket list page and conversations), three with attachments, plus one per new contact and company. Freshdesk's limit depends on the plan (Growth ~200 calls a minute, Pro ~400). 16,000 tickets therefore take roughly one to three hours. The client waits when Freshdesk answers 429. Run the full import **before** downgrading the Freshdesk plan, while the limit is higher.

Failures on single tickets are logged to the Error Log (`/app/error-log`, titled "Freshdesk import: ticket N") and do not stop the run. Re-running retries them.

## Before you cancel Freshdesk

Also take Freshdesk's own export (Admin → Account → Export data) and keep it. The importer covers what the desk needs. The export is the complete record.
