# Freshdesk import

Moves Freshdesk history into Helpdesk. It runs inside the bench, talks to the Freshdesk API v2, and can be run as often as needed: every record keeps its Freshdesk ID, and anything already imported is skipped.

## What comes over

| Freshdesk | Helpdesk |
|---|---|
| Solution categories, folders, articles | HD Article Category, HD Article (published or draft) |
| Groups | HD Team |
| Companies | HD Customer |
| Contacts (requesters) | Contact, linked to their HD Customer |
| Tickets | HD Ticket with **the same number** (e.g. #15919), subject, description, priority, type, team, tags, status, dates |
| Public replies | Email messages on the ticket, with the original dates and senders |
| Private notes | Internal comments (by the agent if they exist in Helpdesk, otherwise marked "Note by … in Freshdesk") |
| Attachments (optional) | Private files on the message and the ticket, up to 20 MB each |

Statuses: Open → Open, Pending → Replied, Resolved → Resolved, Closed → Closed; custom statuses → Open. Closed and resolved history gets no SLA, so SLA reports describe the new desk only. Open tickets are assigned to the same agent, if that agent exists in Helpdesk.

## While it runs

- **No email.** The importer refuses to start unless `mute_emails` is set on the site.
- **No auto-assignment.** Assignment rules for HD Ticket are paused and turned back on afterwards, even if the import fails.
- **No Discord posts.**
- Ticket numbering continues after the highest imported Freshdesk number.

## Run it

```bash
C="docker compose -f deploy/compose.yaml --env-file deploy/.env"
SITE=support.runonflux.io
$C exec backend bench --site $SITE set-config mute_emails 1
$C exec backend bench --site $SITE set-config freshdesk_domain runonflux.freshdesk.com
$C exec backend bench --site $SITE set-config freshdesk_api_key '<admin API key>'

# 1. Count only, change nothing
$C exec backend bench --site $SITE execute flux_helpdesk.importer.freshdesk.run --kwargs '{"dry_run": true}'
# 2. A small real batch, then look at the tickets in /helpdesk
$C exec backend bench --site $SITE execute flux_helpdesk.importer.freshdesk.run --kwargs '{"limit": 50}'
# 3. Everything (add "attachments": true to bring files)
$C exec backend bench --site $SITE execute flux_helpdesk.importer.freshdesk.run

# Afterwards, remove the key from the site config
$C exec backend bench --site $SITE set-config freshdesk_api_key ''
```

Use the account domain (`runonflux.freshdesk.com`), not the portal domain; the API does not answer on the portal. The key must belong to an **admin** so every ticket and note is visible.

| Argument | Default | Meaning |
|---|---|---|
| `limit` | all | Stop after this many tickets |
| `since` | 2000-01-01 | Only tickets updated since (ISO date); use for the final top-up |
| `tickets` / `articles` | true | Skip either part |
| `attachments` | false | Download attachments |
| `assign_open` | true | Assign open tickets to their Freshdesk agent |
| `dry_run` | false | Count only |

## Time and rate limits

Each ticket costs about two API calls (ticket list page and conversations), plus one per new contact and company. Freshdesk's limit depends on the plan (Growth ~200 calls a minute, Pro ~400). 16,000 tickets therefore take roughly one to three hours. The client waits when Freshdesk answers 429. Run the full import **before** downgrading the Freshdesk plan, while the limit is higher.

Failures on single tickets are logged to the Error Log (`/app/error-log`, titled "Freshdesk import: ticket N") and do not stop the run. Re-running retries them.

## Before you cancel Freshdesk

Also take Freshdesk's own export (Admin → Account → Export data) and keep it. The importer covers what the desk needs. The export is the complete record.
