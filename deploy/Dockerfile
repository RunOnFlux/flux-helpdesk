# syntax=docker/dockerfile:1
#
# Flux Helpdesk image: the official Frappe Helpdesk image plus this app.
# Build from the repository root:
#   docker build -f deploy/Dockerfile -t flux-helpdesk:local .
#
# Upgrading Helpdesk = bumping HELPDESK_VERSION, rebuilding, and letting the
# migrate service in compose.yaml run. Nothing of Helpdesk is modified.

ARG HELPDESK_IMAGE=ghcr.io/frappe/helpdesk
ARG HELPDESK_VERSION=v1.30.2
FROM ${HELPDESK_IMAGE}:${HELPDESK_VERSION}

USER frappe
WORKDIR /home/frappe/frappe-bench

COPY --chown=frappe:0 pyproject.toml README.md LICENSE apps/flux_helpdesk/
COPY --chown=frappe:0 flux_helpdesk apps/flux_helpdesk/flux_helpdesk

# The image keeps built assets in ./assets and links them into the sites
# volume on start, so our static files only need a link there. No JS build.
RUN ./env/bin/pip install --no-cache-dir -e apps/flux_helpdesk \
  && ln -sfn /home/frappe/frappe-bench/apps/flux_helpdesk/flux_helpdesk/public \
       /home/frappe/frappe-bench/assets/flux_helpdesk

LABEL org.opencontainers.image.source="https://github.com/RunOnFlux/flux-helpdesk" \
      org.opencontainers.image.description="Frappe Helpdesk with the Flux add-on" \
      org.opencontainers.image.licenses="AGPL-3.0-only"
