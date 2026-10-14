# Flux Helpdesk

Flux's support desk, built on [Frappe Helpdesk](https://github.com/frappe/helpdesk) (open source, AGPL-3.0). This repository holds everything Flux adds on top of it. Helpdesk itself is not forked, so upgrading it stays a version bump.

| Piece | What it does | Where |
|---|---|---|
| **Flux theme** | Flux colours and fonts for the agent and customer app, dark by default | `flux_helpdesk/theme.py`, `public/css/flux-theme.css` |
| **Support page** | `/support`: ask Flux AI first, then open a ticket with the answer attached; your tickets; popular articles | `flux_helpdesk/www/support/` |
| **Ask Flux AI for agents** | A button on every ticket that drafts an answer from the Flux knowledge bot | `flux_helpdesk/ai.py`, `form_scripts/ask_flux_ai.js` |
| **Discord alerts** | New tickets, customer replies and urgent tickets posted to the team channel, linked back to the ticket | `flux_helpdesk/discord.py` |
| **Freshdesk importer** | Moves tickets, conversations, contacts, companies and help articles over from Freshdesk, resumable | `flux_helpdesk/importer/` |
| **MCP server** | Lets Claude and other AI agents search, read and answer tickets | `mcp/` |
| **Deployment** | Docker image and Compose file with backups and automatic migrations | `deploy/` |

The knowledge bot is [RunOnFlux/ownllm](https://github.com/RunOnFlux/ownllm). The support bot that answers tickets by itself is a separate, private service that talks to Helpdesk through its API.

## Quick start (local)

```bash
cp deploy/.env.example deploy/.env       # set SITE_NAME=helpdesk.localhost and two passwords
docker compose -f deploy/compose.yaml --env-file deploy/.env up -d --build
docker compose -f deploy/compose.yaml --env-file deploy/.env logs -f migrate   # wait for "site ready"
```

Then open http://localhost:8080/support (customers) and http://localhost:8080/helpdesk (agents). Log in as `Administrator` with the `ADMIN_PASSWORD` you set.

For development, add `-f deploy/compose.dev.yaml` to run the app from your checkout, and load demo data with `bench --site helpdesk.localhost execute flux_helpdesk.setup.demo.seed` (needs `developer_mode`).

The published Helpdesk image is x86-64 only. On Apple Silicon it runs under emulation, which is slow but fine for testing.

## Install into an existing bench

```bash
bench get-app https://github.com/RunOnFlux/flux-helpdesk
bench --site your.site install-app flux_helpdesk
```

Helpdesk must already be installed on the site (it is a required app).

## Settings

Everything is configured in **Flux Helpdesk Settings** (`/app/flux-helpdesk-settings`):

- **Theme:** on/off, dark by default.
- **Knowledge bot:** URL and optional API key, plus switches for the support page and the agent button.
- **Discord:** webhook, server ID, role to ping for urgent tickets, and which events to post.
- **Support page:** product list, Discord invite and status page links.

## Documentation

- [Architecture](docs/architecture.md): how the pieces fit together
- [Deployment](docs/deploy.md): Compose, backups, TLS, email
- [Upgrading](docs/upgrade.md): Helpdesk and Frappe upgrades
- [Email](docs/email.md): connecting support@runonflux.io
- [Discord](docs/discord.md)
- [AI](docs/ai.md): the knowledge bot and the support bot
- [Freshdesk import](docs/freshdesk-import.md)
- [MCP server](mcp/README.md)
- [Theming](docs/theming.md)

## Development

```bash
pip install ruff pytest beautifulsoup4
ruff check . && ruff format --check .
pytest flux_helpdesk/tests -q          # the tests that need no bench
```

Tests that need a site run inside the bench: `bench --site test.localhost run-tests --app flux_helpdesk`.

## Licence

AGPL-3.0, the same as Frappe Helpdesk. If you run a modified copy that people use over a network, you must offer them its source. This repository is that source for Flux's deployment.

Fonts: Figtree and IBM Plex Mono, both under the SIL Open Font License (see `flux_helpdesk/public/fonts`). The Flux name and logo are trademarks of their owner and are not covered by the AGPL.
