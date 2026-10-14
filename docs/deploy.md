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
# Keep MUTE_EMAILS=1 until email and the import are done.
docker compose -f deploy/compose.yaml --env-file deploy/.env up -d --build
docker compose -f deploy/compose.yaml --env-file deploy/.env logs -f migrate     # "site ready"
```

The `migrate` service creates the site with Helpdesk and this app the first time, and runs `bench migrate` on every later start.

## TLS and the domain

`frontend` (nginx) listens on `127.0.0.1:8080` by default. Put a TLS-terminating proxy in front (Caddy, Traefik, Cloudflare Tunnel or nginx) and send `support.runonflux.io` to it. Then set `UPSTREAM_REAL_IP_ADDRESS` to the proxy's address so rate limits see real client IPs.

At cutover, move the DNS record for `support.runonflux.io` from Freshdesk to this host.

## Backups

The `backup` service runs `bench backup --with-files --compress` once a day and keeps 14 days in `sites/<site>/private/backups` inside the `sites` volume. That only protects against mistakes, not against losing the host. Copy the folder off the host every night, for example:

```bash
docker run --rm -v fluxhd_sites:/sites:ro -v /srv/offsite:/out alpine \
  sh -c 'cp -r /sites/*/private/backups /out/'
# then rclone /srv/offsite to object storage
```

Restore: `bench --site <site> restore <db.sql.gz> --with-public-files <public.tar> --with-private-files <private.tar>`.

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
