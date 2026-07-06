# Deploying SubstanceGuard with $0 cost and no card, anywhere

This splits the 4-service stack across four separately-hosted free tiers, each of which
has historically allowed signup with just an email/GitHub account -- no payment method
requested at any point. This is a different shape from `DEPLOY.md` (which runs the whole
`docker-compose.yml` stack unchanged on one VPS): here, each service is deployed and
configured independently, and they talk to each other over the public internet instead
of a private Docker network.

**Trade-off to accept**: Neo4j Aura Free and Render's free web service both sleep/pause
after a period of inactivity. Aura Free needs a manual "Resume" click in its console
after a few days idle; Render's free web service cold-starts (~30-60s) on the first
request after ~15 minutes idle. Fine for a demo/portfolio project people check out
occasionally; not fine for something expected to respond instantly at 3am.

**Policy note**: free-tier terms change. Confirm each signup below genuinely doesn't
prompt for a card before proceeding -- if one of them starts requiring billing info by
the time you read this, stop and tell me, we'll swap that one piece out.

## Piece 1: Neo4j Aura Free (the graph)

1. https://console.neo4j.io -> sign up with Google/GitHub/email.
2. Create a **Free** instance (AuraDB Free). Choose any region.
3. Aura shows you a **connection URI** (`neo4j+s://xxxxxxxx.databases.neo4j.io`), the
   username (`neo4j`), and a **generated password shown exactly once** -- save all
   three immediately, there is no way to see the password again (only reset it).
4. That's it -- no schema/data to load manually, `app/main.py`'s startup lifespan
   (`apply_schema` + `load_regulatory_data`) does that automatically on first API
   request/boot, same as local dev.

## Piece 2: Qdrant Cloud Free (the vector store)

1. https://cloud.qdrant.io -> sign up with Google/GitHub/email.
2. Create a **Free tier cluster** (1GB, no card).
3. From the cluster's dashboard, copy the **cluster URL** (`https://xxxxxxxx.cloud.qdrant.io`,
   note the port shown, usually `:6333`) and generate an **API key**.
4. This project already supports `QDRANT_API_KEY` (see `app/rag/qdrant_client.py`) --
   nothing else to configure here.

## Piece 3: Render free web service (FastAPI)

1. Push this repo to GitHub if it isn't already (`git remote add origin <url> && git push -u origin master`).
2. https://render.com -> sign up with GitHub (no card for free web services).
3. **New +** -> **Web Service** -> connect your GitHub repo.
4. Runtime: **Docker** (Render detects the `Dockerfile` automatically).
5. Instance type: **Free**.
6. Environment variables (Render's dashboard, **Environment** tab) -- add all of these:

   | Key | Value |
   |---|---|
   | `NEO4J_URI` | the `neo4j+s://...` URI from Piece 1 |
   | `NEO4J_USER` | `neo4j` |
   | `NEO4J_PASSWORD` | the password from Piece 1 |
   | `QDRANT_URL` | the cluster URL from Piece 2 (include `:6333` if shown) |
   | `QDRANT_API_KEY` | the API key from Piece 2 |
   | `GEMINI_API_KEY` | your Gemini key |
   | `GEMINI_MODEL` | `gemini-3.1-flash-lite` (or whichever model has quota -- see this project's README for the free-tier quota ceilings discovered during development) |
   | `GEMINI_EMBEDDING_MODEL` | `gemini-embedding-001` |
   | `LLM_PROVIDER` | `gemini` |
   | `APP_ENV` | `prod` |

7. Deploy. Render assigns a random port via `$PORT` -- the Dockerfile already reads it
   (`CMD sh -c "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"`), so no
   further config needed there.
8. Once live, note the public URL Render gives you, e.g. `https://substanceguard-api.onrender.com`.
   Confirm `https://<that-url>/health` returns `{"status":"ok"}` (the very first request
   will be slow -- Aura/Qdrant Cloud connections + the cold start).

## Piece 4: Streamlit Community Cloud (the UI)

1. https://share.streamlit.io -> sign in with GitHub, **New app**, pick this repo,
   branch, and `streamlit_app.py` as the entry point.
2. Before/after deploying, open **Settings > Secrets** and add:

   ```toml
   API_BASE_URL = "https://substanceguard-api.onrender.com"
   ```

   (`streamlit_app.py` already reads `st.secrets["API_BASE_URL"]` first, falling back to
   the `API_BASE_URL` env var, then to `http://localhost:8000` for local dev -- see the
   top of that file.)
3. Deploy. Streamlit Cloud is free with no card, but also sleeps a public app after a
   period of no visitors -- the first visitor after that wakes it (a visible "waking up"
   screen), same as the sibling Text-to-SQL project already deployed this way.

## Verifying the whole thing end to end

1. Open your Streamlit Cloud URL.
2. Upload one of `db/synthetic_sds/pdfs/doc-01.pdf` through `doc-26.pdf` (all 26 are
   committed to the repo) in the "Screen a Document" tab.
3. Expect it to be slow the first time (Render cold start + Aura connection), then fast
   on subsequent uploads while everything stays warm.
4. Check the "Review Queue" tab picks up any `NEEDS_REVIEW` items and that
   approve/reject round-trips back to Render correctly.

## What you're giving up vs. the VPS path (`DEPLOY.md`)

- No single place to `docker compose logs -f` everything -- logs are in three separate
  dashboards (Render, Aura, Qdrant Cloud).
- Cold starts, as above.
- Free-tier resource caps (Aura Free: 200k nodes/400k relationships -- this project uses
  ~254 Substance nodes plus whatever Product/Component nodes your own screening creates,
  nowhere near the limit; Qdrant Free: 1GB, this project's RAG corpus is a few dozen KB).
- No built-in HTTPS-with-your-own-domain step like the VPS path's Caddy option -- Render
  and Streamlit Cloud both give you a free HTTPS subdomain already, which is enough here.
