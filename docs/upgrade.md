# Upgrading

## Helpdesk (every few weeks)

1. Read the release notes: https://github.com/frappe/helpdesk/releases
2. Set `HELPDESK_VERSION` in `deploy/.env` (for example `v1.31.0`) and update the default in `deploy/Dockerfile` and `deploy/compose.yaml` in the same pull request.
3. On staging, back up first, then rebuild and start: `docker compose … up -d --build`. The `migrate` service runs the database migrations and re-applies our custom fields and the agent button.
4. Check:
   - `/support` loads, Ask Flux AI answers.
   - `/helpdesk` is in the Flux theme (dark navy, blue primary buttons).
   - A ticket shows the **Ask Flux AI** button and the Product / App or node fields.
   - A test ticket posts to Discord, if that is turned on.
5. Do the same on production.

Never skip several Frappe framework major versions at once. Helpdesk images pin their own Frappe version, so following Helpdesk releases one at a time keeps that safe.

## If the theme looks wrong after an upgrade

Helpdesk still works; it has fallen back to its stock look. frappe-ui probably renamed a design token. Compare the variable names in the new build:

```bash
docker run --rm --entrypoint bash ghcr.io/frappe/helpdesk:<version> -c \
  'cat /home/frappe/frappe-bench/assets/helpdesk/desk/assets/*.css' | grep -o -- '--surface-[a-z0-9-]*' | sort -u
```

and update `flux_helpdesk/public/css/flux-theme.css`.

## This app

Merging to `main` and rebuilding is enough. Custom fields and the form script are re-applied on every migrate, so there is no separate install step.

## Frappe major version (v15 → v16)

This app supports Frappe 15 and 16 (`pyproject.toml`). When the Helpdesk image moves to Frappe 16, test it on staging with a copy of production data before upgrading production.
