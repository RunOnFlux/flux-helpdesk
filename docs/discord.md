# Discord alerts

Posts ticket cards to a team channel, such as `#support-tickets`, through a channel webhook.

| Event | When | Ping |
|---|---|---|
| New ticket | A ticket is created (email, portal, /support) | none |
| Customer replied | A customer answers on an existing ticket | none |
| Raised to Urgent | Priority changes to Urgent | the role you set |

Each card links to the ticket. For new tickets, the Discord message link is saved on the ticket, and agents see a **Discord** button in the ticket header.

## Set up

1. In Discord: channel → Edit Channel → Integrations → Webhooks → New Webhook. Copy the URL. Treat it as a secret: anyone with it can post in that channel.
2. Turn on Developer Mode (User Settings → Advanced), then right-click the server and **Copy Server ID**. For pings, right-click the role and **Copy Role ID**.
3. In **Flux Helpdesk Settings → Discord**: turn it on, paste the webhook, server ID and role ID, and pick the events.

## Safety

- Customer text never pings anyone. Every post sets `allowed_mentions.parse` to empty, and Markdown in customer text is escaped, so a customer cannot create links or formatting.
- Imports and migrations never post (`frappe.flags.in_import`, `flux_importing`).
- Posting happens in a background job after the database commit. A Discord outage never blocks a ticket.

## With the support bot

The support bot (influx-agents) already posts its own triage cards to `#support-tickets`: what it answered, why it escalated, reminders and a daily digest. If both run, turn off **New tickets** here, or point this webhook at a different channel, so each ticket shows up once.

## Later: replying from Discord

Replying to customers from a Discord thread needs a Discord bot (not a webhook) that reads the thread and calls Helpdesk's API. That belongs in the support bot service, which already holds Discord access. It is not built yet.
