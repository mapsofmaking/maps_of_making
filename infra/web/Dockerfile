# The app's web server: Caddy with web/ and ontology/ baked in. Build context = repo root
# (see /.dockerignore). web/data and web/canary are written at runtime and
# mounted over /srv/data and /srv/canary by compose.
FROM caddy:2.11.4-alpine
COPY infra/web/Caddyfile /etc/caddy/Caddyfile
COPY web/ /srv/
# The vocabulary, served at /ns/ (Caddyfile).
COPY ontology/ /ns/
