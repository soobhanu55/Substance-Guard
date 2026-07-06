# Deploying SubstanceGuard to a VPS

This stack is 4 services (Neo4j, Qdrant, FastAPI, Streamlit) run via the existing
`docker-compose.yml`, which is the reason a single small VPS running docker-compose is
the simplest deploy target -- no code changes needed, just a hardened compose overlay
(`docker-compose.prod.yml`) that closes off direct database access from the internet.

## 1. Pick a server -- $0 option: Oracle Cloud "Always Free" Ampere VM

Neo4j is the only memory-hungry piece here (256MB pagecache + 512MB heap configured);
Qdrant/FastAPI/Streamlit are all light for this project's data volume. **4GB RAM / 2 vCPU
is comfortable headroom, 2GB is the bare minimum and leaves little slack.**

**Oracle Cloud's Always Free tier** includes an Ampere (ARM, `VM.Standard.A1.Flex`)
allowance of up to **4 OCPU / 24GB RAM total, genuinely free forever** (not a trial
credit) -- easily enough for this whole stack with room to spare. This project's images
(`python:3.12-slim`, `neo4j:5.26-community`, `qdrant/qdrant`, `caddy:2.8-alpine`) are all
official multi-arch images that publish ARM64 builds, so nothing in this repo needs to
change to run on it.

1. Sign up at https://signup.cloud.oracle.com. A card is required for identity
   verification -- you are not charged unless you explicitly upgrade to a paid account.
   Pick your Home Region carefully during signup (it cannot be changed later); Always-Free
   Ampere capacity availability varies by region and is sometimes exhausted -- if you hit
   "out of capacity" when creating the instance, retrying after a few minutes/hours (or
   trying a different Always-Free-eligible region) is a known, common workaround.
2. In the OCI Console, use the **Create a VM instance** quickstart
   (hamburger menu > Compute > Instances > Create Instance):
   - Under **Image and shape**, click **Change shape** > **Ampere** > `VM.Standard.A1.Flex`,
     set **4 OCPUs** / **24 GB memory** (the full Always Free allowance).
   - Image: **Canonical Ubuntu 24.04** (the image list updates to ARM-compatible builds
     once you've selected the Ampere shape).
   - Under **Add SSH keys**, paste your SSH **public** key (generate one with
     `ssh-keygen -t ed25519` if you don't have one).
   - Click **Create**.
3. **Open the cloud-level firewall** (separate from the OS firewall in step 2 below --
   Oracle's default Security List blocks everything but SSH by default): go to
   **Networking > Virtual Cloud Networks** > (the VCN created for you) > your subnet's
   **Security List** > **Add Ingress Rules**. Add rules for source `0.0.0.0/0`,
   destination port ranges `8000`, `8501`, and (only if you'll add a domain + HTTPS
   later) `80` and `443`.
4. Note the instance's public IPv4 address from the instance details page.

**Paid alternative, if you'd rather not deal with Oracle's signup/capacity quirks:
Hetzner Cloud CX22** (2 vCPU, 4GB RAM, ~EUR 4.35/mo, console at
https://console.hetzner.cloud) -- same steps as above minus the extra cloud-firewall
layer (Hetzner has none by default; only the OS-level `ufw` in step 2 applies).

## 2. Initial server setup

SSH in (`ssh ubuntu@<server-ip>` on Oracle's Ubuntu image -- note: **not** `root`, use
`sudo` instead, or `ssh root@<server-ip>` on Hetzner) and run:

```bash
sudo apt-get update && sudo apt-get upgrade -y
curl -fsSL https://get.docker.com | sudo sh     # installs Docker + Compose plugin (auto-detects arm64/amd64)
sudo usermod -aG docker $USER && newgrp docker  # so you don't need sudo for docker commands
sudo apt-get install -y ufw git
sudo ufw allow 22/tcp
sudo ufw allow 8000/tcp   # FastAPI -- skip this and 8501 below if you'll only use the Caddy/HTTPS path
sudo ufw allow 8501/tcp   # Streamlit
sudo ufw allow 80/tcp     # only needed if enabling Caddy (step 6)
sudo ufw allow 443/tcp    # only needed if enabling Caddy (step 6)
sudo ufw --force enable
```

(On Oracle, this OS-level firewall is *in addition to* the cloud-level Security List
rules from step 1.3 above -- both layers must allow a port for it to be reachable.)

## 3. Get the code onto the server

```bash
git clone <your-repo-url> ~/substanceguard
cd ~/substanceguard
```

(If you haven't pushed this repo anywhere yet: `git init && git remote add origin <url>
&& git push -u origin master` from your machine first, or `scp -r` the directory instead
of cloning.)

## 4. Configure production secrets

```bash
cp .env.production.example .env
nano .env   # fill in GEMINI_API_KEY, and set NEO4J_PASSWORD to a real random value:
            #   openssl rand -base64 24
```

**Do not deploy with the dev default `NEO4J_PASSWORD=substanceguard`** -- `docker-compose.prod.yml`
already stops Neo4j/Qdrant from being published to the internet, but the password still
matters for defense-in-depth (any container on the same Docker network, or a future
misconfiguration, would otherwise have a well-known credential).

## 5. Bring the stack up

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
docker compose ps   # wait for all 4 to show "healthy"
curl http://localhost:8000/health
```

Visit `http://<server-ip>:8000/health` and `http://<server-ip>:8501` from your own
browser to confirm it's reachable publicly.

## 6. Optional: a real domain + automatic HTTPS

If you have a domain, point two DNS A records at the server's IP (e.g.
`app.yourdomain.com` and `api.yourdomain.com`), then:

```bash
# add DOMAIN_APP and DOMAIN_API to .env (see .env.production.example), then:
ufw delete allow 8000/tcp   # no longer needed publicly -- Caddy fronts it now
ufw delete allow 8501/tcp
docker compose -f docker-compose.yml -f docker-compose.prod.yml --profile with-https up -d
```

Caddy (`Caddyfile`) requests and renews Let's Encrypt certificates automatically on
first request to each domain -- no manual certbot steps.

## 7. Redeploying updates

```bash
cd ~/substanceguard
git pull
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

(`deploy.sh` in this repo wraps exactly this, run it from the server after a `git pull`.)

## 8. Logs, backups

```bash
docker compose logs -f api          # tail one service
docker compose logs -f              # tail everything
```

The regulatory graph and vector data live in the `neo4j_data` and `qdrant_data` named
volumes (both re-populated automatically from `db/regulatory_data/` on API startup if
ever lost, since `app/main.py`'s lifespan runs the loader/ingest idempotently) -- so there
is nothing irreplaceable to back up beyond the `.env` file itself and anything in the
`data/` review-queue/checkpoint store if you care about in-flight human-review state.

## Cost summary

- Oracle Cloud Always Free Ampere VM: **$0/mo, forever**, no trial expiry (card on file
  is for identity verification only; nothing is charged while you stay within the
  Always Free shape/OCPU/memory limits above)
- Gemini API: free tier has real, low daily/per-minute quota ceilings (this project's own
  README documents the exact numbers hit during development) -- pay-as-you-go only if you
  exceed them; $0 for light/demo use
- Domain (optional, for the Caddy/HTTPS step): ~$10-15/yr if you don't already have one --
  skip it entirely and use the plain `http://<ip>:8501` / `:8000` URLs for $0
