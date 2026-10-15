# Deployment

One host with Docker Compose is enough for Flux's volume (about 16,000 tickets over four years). The app containers are stateless. All state is in MariaDB, Redis (queue) and the `sites` volume.

## Size

About 2–4 vCPUs, 4–8 GB RAM and 40 GB disk to start. No Elasticsearch is needed. Attachments grow the `sites` volume; budget for the Freshdesk attachments if you import them.

The published Helpdesk image is x86-64 only, so use an x86-64 host.

## First start

```bash
git clone https://github.com/RunOnFlux/flux-helpdesk && cd flux-helpdesk
cp deploy/.env.example deploy/.env
# Set SITE_NAME=support.runonflux.io, ADMIN_PASSWORD, DB_ROOT_PASSWORD (long random strings).
# Keep MUTE_EMAILS=1 until email and the import are done. It is re-applied on every `up`.
docker compose -f deploy/compose.yaml --env-file deploy/.env up -d --build
docker compose -f deploy/compose.yaml --env-file deploy/.env logs -f migrate     # "site ready"
```

The `migrate` service creates the site with Helpdesk and this app the first time, and runs `bench migrate` on every later start. It also turns the scheduler on (`ENABLE_SCHEDULER=1`): a new Frappe site starts with it off, and without it no email is fetched, SLAs do not update and nothing auto-closes. The app containers wait for it, so after an upgrade they only start once the database is migrated. If `migrate` fails, nothing new starts; read `logs migrate`.

## TLS and the domain

`frontend` (nginx) listens on `127.0.0.1:8080` by default. Put a TLS-terminating proxy in front (Caddy, Traefik, Cloudflare Tunnel or nginx) and send `support.runonflux.io` to it. The proxy must set `X-Forwarded-For`.

nginx only believes `X-Forwarded-For` from `UPSTREAM_REAL_IP_ADDRESS`, which defaults to `172.16.0.0/12`, Docker's bridge range: a proxy on the host reaches the published port from the bridge gateway, not from 127.0.0.1. If Docker on the host uses other ranges (`docker network inspect` on the project network), set it to match. Without this every visitor looks like the same address, and per-IP limits such as Ask Flux AI's become one shared limit. Behind Cloudflare, have the proxy take the client address from `CF-Connecting-IP`.

At cutover, move the DNS record for `support.runonflux.io` from Freshdesk to this host.

## Backups

The `backup` service runs `bench backup --with-files --compress` when it starts and then once a day, and keeps 14 days (`keep_backups_for_hours` is set to 336; bench would otherwise delete everything older than a day on each run). The files sit in `sites/<site>/private/backups` inside the `sites` volume. That only protects against mistakes, not against losing the host. Copy the folder off the host every night, for example:

```bash
docker run --rm -v fluxhd_sites:/sites:ro -v /srv/offsite:/out alpine \
  sh -c 'cp -r /sites/*/private/backups /out/'
# then rclone /srv/offsite to object storage
```

Each backup is four files: the database (`-database.sql.gz`), public files, private files and `-site_config_backup.json`. **Keep the site config with the rest.** It holds `encryption_key`, which every password field is encrypted with: the mail account, the Discord webhook, the knowledge bot key and API secrets. Restore on a new host:

```bash
# copy encryption_key from *-site_config_backup.json into sites/<site>/site_config.json first
bench --site <site> restore <db.sql.gz> --with-public-files <public.tar> --with-private-files <private.tar>
bench --site <site> migrate
```

Test a restore on a scratch host once, before relying on it.

## Settings after the first start

1. Log in at `/login` as `Administrator`, open `/helpdesk` and finish Helpdesk's setup. Set the time zone in System Settings (`/app/system-settings`) before importing anything; dates are stored in it.
2. **Flux Helpdesk Settings** (`/app/flux-helpdesk-settings`): knowledge bot API key, Discord webhook, links.
3. Email: see [email.md](email.md).
4. Agents: invite them from Helpdesk → Agents. There is no per-seat limit.

## Commands

```bash
C="docker compose -f deploy/compose.yaml --env-file deploy/.env"
$C exec backend bench --site support.runonflux.io console     # Python console
$C exec backend bench --site support.runonflux.io mariadb     # SQL
$C logs -f backend queue-short                                 # logs
```

## Bare metal

Without Docker, use a normal Frappe bench (`bench init`, `bench get-app helpdesk`, `bench get-app https://github.com/RunOnFlux/flux-helpdesk`, `bench new-site`, `bench --site … install-app helpdesk flux_helpdesk`, `bench setup production`). The Frappe docs cover production setup with nginx and supervisor.
