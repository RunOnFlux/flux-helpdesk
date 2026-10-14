# AI

Three separate things use AI around the desk.

## 1. Flux AI on /support (customers)

Customers ask before they open a ticket. The page sends the question to `flux_helpdesk.ai.ask`, which forwards it to the knowledge bot's `/ask` endpoint and returns the answer and its sources. If it does not help, the customer opens a ticket from the same screen with the question and the answer attached, so nobody has to ask again.

- Rate limit: 10 questions per minute per IP address, on our side.
- Set a **knowledge bot API key** in Flux Helpdesk Settings. Without one, every customer's question reaches the bot from this server's single IP address and shares the bot's per-IP limit.
- The bot answers only from Flux's public documentation ([RunOnFlux/ownllm](https://github.com/RunOnFlux/ownllm)). When the docs do not cover something, it says so, and the page offers a ticket.

## 2. Ask Flux AI (agents)

A button in every ticket's header. It sends the subject and the latest customer message to the bot and shows the suggested answer with sources, plus a copy button. Nothing is sent to the customer; the agent decides. The button is an HD Form Script named `Flux: Ask Flux AI`, installed and updated on every migrate from `flux_helpdesk/form_scripts/ask_flux_ai.js`.

## 3. The support bot (private, influx-agents)

The bot that answers tickets by itself is not in this repository. It reads unassigned tickets through the Helpdesk REST API, drafts answers from solved tickets, the help centre, docs and code, and then either sends the answer, waits for approval, or escalates to a person with a private note. Its escalation rules (money, security, legal, seed phrases, low confidence) are code, and it keeps them private on purpose.

To connect it to Helpdesk:

1. Create an agent user for it, for example "Flux Support AI", in every team.
2. Generate API keys for that user (User → Settings → API Access).
3. Give the bot the site URL and the key and secret. Its Helpdesk connector uses:
   - `GET /api/resource/HD Ticket`: open, unassigned tickets
   - `GET /api/resource/Communication`: the conversation
   - `run_doc_method` `reply_via_agent` / `new_comment`: reply or private note
   - `PUT /api/resource/HD Ticket/<id>`: status, priority, team, tags

The [MCP server](../mcp/README.md) wraps the same calls, if you want Claude to work tickets directly.
