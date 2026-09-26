# SEO Visibility Panel

A focused, self-hosted dashboard for two things:

- **AI Visibility** — for each keyword, does Google's AI Overview appear, are you cited, and who is cited instead.
- **Map Grid** — your Google map-pack rank from every point across a grid of GPS coordinates, with run-over-run history.

It is a from-scratch replacement for the AI Visibility + Map Grid parts of
[seo-command-center](https://github.com/alfoncastellote/seo-command-center),
built as a single FastAPI service with a real backend (no Cloudflare KV), so it
runs cleanly behind Coolify with its own login, scheduler and SQLite history.

## Stack

- Python 3.12 + FastAPI + Uvicorn (single container)
- SQLite for storage (mounted volume at `/app/data`)
- Server-rendered shell + vanilla JS; Leaflet for the map (Esri dark basemap)
- Server-side job worker and weekly scheduler (background threads)
- DataForSEO pay-as-you-go (same provider as the original)

## Features

**AI Visibility**
- Per-brand keyword sets (target / brand / seed tiers)
- Scan: AI Overview presence, whether your domain is cited, and the domains cited instead
- KPIs, citation-leader board, keyword table with filters, citation trend over time

**Map Grid**
- Grid setup: center, size (5/7/9), spacing, up to 10 keywords per grid
- Colored pins per point, top-3 per pin, run selector, compare-to-previous deltas
- Coverage KPIs and trend chart

**Both**
- Access-key login
- Daily run caps (protect API credits) and configurable concurrency
- Weekly automatic refresh per tool
- Brand & keyword management from the UI
- All runs stored forever

## Run locally

```bash
pip install -r requirements.txt
export ACCESS_KEY=testkey
export DATA_DIR=./data
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open http://localhost:8000, sign in, then either add a brand under
**Brands & keywords** or press **Load demo data** in **Settings** to explore the
UI without API credentials.

## Configuration (environment variables)

| Variable | Default | Purpose |
| --- | --- | --- |
| `ACCESS_KEY` | `changeme` | Login key. **Set this.** |
| `SESSION_SECRET` | derived from `ACCESS_KEY` | Cookie signing secret |
| `DATAFORSEO_LOGIN` / `DATAFORSEO_PASSWORD` | — | DataForSEO API credentials |
| `BRAND_NAME` | `SEO Visibility` | Name shown in the UI |
| `DATA_DIR` | `/app/data` | SQLite + legacy import location |
| `PORT` / `HOST` | `8000` / `0.0.0.0` | Bind address |

## Deploy on Coolify

1. Point an application at this repository, build pack **Dockerfile** (`/Dockerfile`).
2. Set **Ports Exposes** to `8000` (the container listens on `0.0.0.0:8000`).
3. Add environment variables: `DATAFORSEO_LOGIN`, `DATAFORSEO_PASSWORD`,
   `ACCESS_KEY`, `SESSION_SECRET`, `BRAND_NAME`.
4. Add a persistent volume mounted at `/app/data` so SQLite survives redeploys.
5. Set the domain and deploy. Health check path: `/healthz`.

The app binds `0.0.0.0` (unlike the original tracker, which bound `127.0.0.1`)
so Traefik/Coolify can reach it.

## Cost control

- Manual runs are capped per day (default 2 for AI Visibility, 1 for Map Grid) and
  the cap is editable in **Settings**.
- Approximate costs: `$0.0035` per AI Visibility keyword, `$0.002` per map pull.
  A 7×7 grid on 2 keywords is 98 pulls ≈ `$0.20`.
- Weekly scheduled runs are not subject to the manual caps.

## Data model

`brands`, `keywords`, `geogrids`, `geogrid_keywords`, `geogrid_points`,
`ai_runs`, `ai_results`, `jobs`, `settings`, `counters` — all in
`/app/data/panel.db`.

On first boot the app imports `keywords.json` and the old `geogrid` table from
`ranks.db` if they exist in `DATA_DIR` (one-time, only when the database is empty).
