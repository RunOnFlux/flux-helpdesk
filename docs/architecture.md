# Architecture

```
Customers ──► support.runonflux.io/support ──► Flux AI (knowledge bot, /ask)
                    │                                   ▲
                    │ open a ticket                     │ "Ask Flux AI" button
                    ▼                                   │
Email (support@) ─► Frappe Helpdesk ◄── agents at /helpdesk
                    │      ▲
         doc events │      │ REST API (API key of an agent user)
                    ▼      │
            Discord webhook   ├── Support bot (influx-agents, private): answers, triages, escalates
            (#support-tickets)└── MCP server (mcp/): Claude and other AI agents
```

## What runs where

- **Frappe Helpdesk** (upstream, unmodified): tickets, email in and out, SLAs, teams, the agent app at `/helpdesk`, the customer portal and the help centre.
- **flux_helpdesk** (this app, installed next to Helpdesk):
  - `theme.py` adds `flux-theme.css` to the `/helpdesk` page through Frappe's `after_request` hook. The CSS only overrides frappe-ui's design tokens, so Helpdesk's layout and code stay as they are.
  - `www/support/` is our own front page. It is plain Jinja, CSS and a small script with no build step.
  - `ai.py` proxies questions to the knowledge bot, so the browser never talks to it directly and we can rate-limit and add an API key.
  - `discord.py` listens to ticket and email events and posts through a webhook from a background job.
  - `setup/install.py` adds custom fields (product, app or node, Discord link, Freshdesk IDs), installs the agent button as an HD Form Script, and sets branding. It runs on every migrate.
  - `importer/` moves Freshdesk data in once, then is no longer needed.
- **Knowledge bot**: [RunOnFlux/ownllm](https://github.com/RunOnFlux/ownllm), answering from the public docs.
- **Support bot**: the private influx-agents service. It reads new tickets through the Helpdesk API, drafts or sends answers, escalates risky topics to people and posts its own triage cards to Discord.

## Why an add-on and not a fork

Helpdesk ships a new release every one to three weeks. A fork would need merging every time. Everything here goes through extension points Frappe and Helpdesk already have: hooks, custom fields, form scripts, website pages and the REST API. An upgrade is therefore a version bump and a migrate (see [upgrade.md](upgrade.md)).

The one soft spot is the theme. It depends on frappe-ui's CSS variable names (`--surface-*`, `--ink-*`, `--outline-*`) and on solid buttons using `bg-surface-gray-10`. If an upgrade renames them, the desk keeps working and just looks like stock Helpdesk until `flux-theme.css` is updated.

## Data

Everything lives in the site's MariaDB database and the `sites` volume (attachments). Nothing here stores data elsewhere. Customer data never goes into this repository.
