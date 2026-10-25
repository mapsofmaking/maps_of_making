# Deploying the map to the new server

Every push to `mom-vps` builds the images in CI and deploys that commit to
`/srv/mom-map` on the server (workflow `images`, job `deploy`). The server
never builds and is never edited by hand: it holds a checkout (compose file,
mounted scripts), `infra/.env` (secrets) and `data/`.

## How a deploy works

1. CI pushes `ghcr.io/mapsofmaking/{maps-web,maps-link-handler,maps-agent-bot}:sha-<7>`.
2. Job `deploy` (GitHub environment `production`) connects as `deploy` with a
   key that the server forces to `/usr/local/sbin/mom-map-deploy`, and sends
   the commit id. That is all the key can do.
3. The script checks the commit is on `mom-vps`, checks it out, writes
   `MAP_TAG=sha-<7>` in `infra/.env`, then `docker compose pull` and
   `up -d --no-build --wait`. Its log: `journalctl -t mom-map-deploy`.

**Rollback**: re-run the `images` workflow's deploy of an older commit, or on
the server as `deploy`: `mom-map-deploy <older commit id>`.

## One-time setup on the server

Lines with `sudo` are run by an administrator. Nothing secret is printed.

```sh
# 1. The deploy user (in group docker: it runs compose) and the app folder.
sudo useradd --system --create-home --shell /bin/sh --groups docker deploy
sudo install -d -o deploy -g deploy -m 750 /srv/mom-map
sudo -u deploy git clone -q --branch mom-vps https://github.com/mapsofmaking/maps_of_making /srv/mom-map

# 2. infra/.env, secrets generated on the server (600, owner deploy).
sudo -u deploy sh -c 'umask 077; { echo GATEWAY_NETWORK=proxy; echo COMPOSE_PROFILES=; echo "LINK_SECRET=$(openssl rand -hex 32)"; echo "BOT_KEY_SECRET=$(openssl rand -base64 32 | tr -- "+/" "-_")"; } > /srv/mom-map/infra/.env'

# 3. Admin login: type the password at the prompt (not echoed).
printf 'Admin password: '; stty -echo; read -r P; stty echo; echo; H=$(printf '%s\n' "$P" | docker run --rm -i caddy:2.11.4-alpine caddy hash-password); unset P; echo "MAP_ADMIN_PASSWORD_HASH='$H'" | sudo -u deploy tee -a /srv/mom-map/infra/.env >/dev/null

# 4. The deploy script, root-owned copy.
sudo install -o root -g root -m 755 /srv/mom-map/infra/deploy/mom-map-deploy /usr/local/sbin/mom-map-deploy

# 5. CI's public key, forced to the script (key made on the workstation, below).
sudo -u deploy sh -c 'umask 077; mkdir -p ~/.ssh; printf "restrict,command=\"/usr/local/sbin/mom-map-deploy\" %s\n" "$(cat /tmp/mom-map-ci.pub)" >> ~/.ssh/authorized_keys' && rm /tmp/mom-map-ci.pub
```

The secrets of step 2 are fresh, for a test install. At the switch from the
old server, `LINK_SECRET` and `BOT_KEY_SECRET` are replaced by the old
server's values: claim links and stored deploy keys depend on them.

When the deploy script changes in the repo, repeat step 4.

## The key (on the workstation)

```sh
ssh-keygen -q -t ed25519 -N '' -C 'mom-map CI' -f ~/.ssh/mom-map-ci
scp ~/.ssh/mom-map-ci.pub <server>:/tmp/
gh secret set MOM_DEPLOY_KEY --env production -R mapsofmaking/maps_of_making < ~/.ssh/mom-map-ci && rm ~/.ssh/mom-map-ci ~/.ssh/mom-map-ci.pub
```

The private key lives only in the GitHub environment. Lost or leaked: remove
its line from `~deploy/.ssh/authorized_keys` and make a new one.

## GitHub side

- Environment `production`, deployments from `mom-vps` only, with secrets
  `MOM_DEPLOY_KEY`, `MOM_DEPLOY_HOST` and `MOM_DEPLOY_KNOWN_HOSTS` (the
  server's host key line). The host is a secret only to keep it out of a
  public repo's logs.
- Repository variable `MOM_DEPLOY=on` turns the deploy job on.
- The three packages under `ghcr.io/mapsofmaking/` are public, so the server
  pulls without a login.
