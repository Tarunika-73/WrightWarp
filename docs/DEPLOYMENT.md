# Deployment

## Target architecture

| Component | Where | Notes |
|---|---|---|
| Dashboard (React/Vite) | Vercel CDN | built by `vercel.json` `buildCommand` into `frontend/dist`, served at `/` |
| API (FastAPI) | Vercel Function (Python) | entrypoint `index.py` (auto-detected), runtime deps from `pyproject.toml`, `maxDuration` 300 s |
| Database | MongoDB Atlas | connection string in `MONGO_URI` |
| Daily collection | Vercel Cron | `GET /api/v1/cron/daily` at `30 0 * * *` (06:00 IST) |
| Browser-based collection | not deployed | would need a separate worker; see `ARCHITECTURE.md` |

## Environment variables (Vercel → Project → Settings → Environment Variables)

| Name | Required | Value |
|---|---|---|
| `MONGO_URI` | yes | Atlas `mongodb+srv://…` string. URL-encode special characters in the password. |
| `MONGO_DB_NAME` | yes | `wrightwarp` |
| `ENVIRONMENT` | yes | `production` |
| `APP_NAME` | no | `wrightwarp-api` |
| `CRON_SECRET` | yes, for cron | a random string of at least 32 characters. Vercel Cron sends it as `Authorization: Bearer …`. |
| `DEMO_MODE` | no | `true` (default) |
| `INDEX_BASE_YEAR` | no | `2024` |
| `CORS_ORIGINS` | no | only needed if another origin calls the API |

Never commit these. `.env` is in `.gitignore` and `.vercelignore`.

## MongoDB Atlas network access

Vercel functions have no fixed egress IPs on standard plans. Atlas → Network Access must therefore
allow `0.0.0.0/0`, protected by a strong password on a least-privilege user (`readWrite` on
`wrightwarp`, and on `wrightwarp_test*` for running tests). Alternatively, use Vercel's Atlas
integration or Secure Compute.

## Steps

```bash
# 0. Pre-flight (local)
cd backend && .venv/Scripts/python.exe -m pytest -q && cd ..
cd frontend && npm ci && npm run build && cd ..

# 1. Log in and link (interactive once)
npx vercel login
npx vercel link            # create/select project "wrightwarp", root = repo root

# 2. Environment variables (repeat for preview and production as needed)
npx vercel env add MONGO_URI production
npx vercel env add MONGO_DB_NAME production
npx vercel env add ENVIRONMENT production
npx vercel env add CRON_SECRET production

# 3. Preview deploy and verify
npx vercel deploy
curl https://<preview-url>/health/db

# 4. Production
npx vercel deploy --prod
```

## Post-deploy verification

```bash
BASE=https://<production-domain>
for p in / /health /health/db /docs /api/v1/sources /api/v1/routes /api/v1/index \
         /api/v1/collections /api/v1/backtest /api/v1/stats/overview; do
  curl -s -o /dev/null -w "%{http_code} $p\n" "$BASE$p"; done
# Cron endpoint must refuse without the secret:
curl -s -o /dev/null -w "%{http_code}\n" "$BASE/api/v1/cron/daily"      # expect 401
```

## Data

The deployment reads the same Atlas database as local development. Seed or refresh the DEMO history
from a workstation with `python -m app.cli seed-demo`; this is too long for a function invocation.
After that, the daily cron keeps the data moving forward.

## Other hosts

`backend/app/main.py` also serves `frontend/dist` itself when that directory exists. The whole app
can therefore run as a single process anywhere (Render, a VM, a container) with
`uvicorn app.main:app --host 0.0.0.0 --port $PORT` from `backend/`, after
`npm run build` in `frontend/`. No Render configuration exists in this repository. If a Render
service was set up in its dashboard, leave it running as a fallback until the Vercel deployment has
been verified.
