# Shared Expenses App

A Splitwise-style app for a flat whose members change over time. Built for the
Spreetail internship assignment. The headline feature is a **spreadsheet
importer** that ingests a deliberately messy export, detects every data problem,
surfaces it, and handles it by a documented policy — never a silent guess and
never a crash.

- **Live app:** https://likhit37.github.io/Spreetail-Assignment/
- **API:** https://shared-expenses-api-8wuo.onrender.com

## Stack
- **Backend:** Django 5 + Django REST Framework, JWT auth (`djangorestframework-simplejwt`)
- **DB:** PostgreSQL in production (SQLite for local dev) — relational only
- **Frontend:** React (Vite) + React Router
- **Currency:** [Frankfurter](https://frankfurter.dev) historical FX (free, no key)
- **LLM:** Anthropic Claude for the "explain my balance" feature (optional; falls
  back to a deterministic template when no key is set)

## What it does
- Login / register (JWT; each user only sees groups they created or belong to)
- **Manage groups** whose membership changes over time — add a member with a join
  date, or mark when someone left
- **Add expenses** manually in any of four split types — `equal`, `unequal`,
  `percentage`, `share` (ratio); the form only lets you split among members who
  were in the group on the expense's date
- **Settle up** — record a payment between two members (kept separate from
  expenses); each "who pays whom" row has a one-click settle shortcut
- Group balances: net per person **and** a minimal "who pays whom" list
- Per-member drill-down: every expense line behind a balance (no magic numbers)
- **Import wizard:** upload the export → review every anomaly → resolve blockers
  → commit → import report

Manual and imported expenses share the exact same split + FX code, so both
always produce balances that sum to zero.

See [SCOPE.md](SCOPE.md) for the anomaly log + schema, [DECISIONS.md](DECISIONS.md)
for why things are the way they are, and [AI_USAGE.md](AI_USAGE.md) for how AI was
used (and where it was wrong).

## Local setup

### Backend
```bash
cd backend
python -m venv ../.venv
../.venv/Scripts/activate      # Windows;  source ../.venv/bin/activate on macOS/Linux
pip install -r ../requirements.txt
cp .env.example .env           # defaults are fine for local (SQLite, no key)
python manage.py migrate
python manage.py runserver 8000
```

### Frontend
```bash
cd frontend
npm install
cp .env.example .env           # VITE_API_BASE defaults to http://localhost:8000
npm run dev                    # http://localhost:5173
```

### Import the sample file
Log in, create a group, open **Import spreadsheet**, and upload
`expenses_export assigbment annex.xlsx` (unedited). The wizard shows the anomaly
review, then commits and prints the import report.

To generate the import report from the CLI:
```bash
cd backend
python manage.py generate_import_report \
  --file "../expenses_export assigbment annex.xlsx" --out ../import_report.json
```

## Tests
```bash
cd backend
python manage.py test          # 48 tests: split math, balances, auth, detectors,
                                # commit, generic-sheet + robustness cases
```
Detector tests run against the **real, unedited** file, pinning each anomaly to
the exact row that triggers it. A separate set (`GenericSheetTests`,
`RobustnessTests`) proves the importer against synthetic data the roster was
never seeded for — an unrecognised payer, a different sheet's year, a missing
amount/date, and a malformed row that must not take the rest of the batch
down with it.

## Deploy
- **Postgres → Neon:** create a free project at [neon.tech](https://neon.tech)
  (no card) and copy the pooled connection string.
- **Backend → Render:** the repo includes [`render.yaml`](render.yaml). Create a
  Blueprint from the repo; it runs `backend/build.sh` (install, collectstatic,
  migrate) and starts gunicorn. Set env vars: `DEBUG=False`, `SECRET_KEY`,
  `DATABASE_URL` (Neon), `ALLOWED_HOSTS=.onrender.com`, `FX_PROVIDER_URL`, and
  after the frontend is up, `CORS_ALLOWED_ORIGINS` to the GitHub Pages origin
  (`https://<user>.github.io`). Optional `ANTHROPIC_API_KEY` enables the LLM
  feature.
- **Frontend → GitHub Pages:** pushing to `main` runs
  [`.github/workflows/deploy-frontend.yml`](.github/workflows/deploy-frontend.yml),
  which builds the Vite app and publishes it to Pages. Set a repo **variable**
  `VITE_API_BASE` (Settings → Secrets and variables → Actions → Variables) to the
  Render API URL, and enable Pages (Settings → Pages → Source: GitHub Actions).
  The app is served at `https://<user>.github.io/Spreetail-Assignment/`; the Vite
  `base` and router `basename` are configured for that subpath, and a
  `404.html` fallback keeps deep links working.

## AI used
Anthropic **Claude** (via Claude Code, model Opus 4.8) as the primary development
collaborator. Every line was reviewed and is explained in the docs above.
