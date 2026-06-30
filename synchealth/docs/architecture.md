# synchealth — Architecture (MVP 1.0)

## Goals

Self-hosted app to centralise biometric data from **Garmin Connect** and
**Zepp Life**, with the long-term goal of feeding training/nutrition
recommendations. MVP 1.0 ships only the foundation (storage, ingestion
of CSV exports, read APIs, minimal UI) so that later MVPs can bolt on
real integrations without restructuring.

## Components

```
+----------------------+        HTTP        +----------------------+
|   React 18 frontend  |  <--------------->  |   FastAPI backend    |
|   Vite + TypeScript  |     /api/*          |   Python 3.11        |
|   recharts           |                     |   SQLAlchemy 2 async |
+----------------------+                     +----------+-----------+
                                                        |
                                                        | aiosqlite
                                                        v
                                                +---------------+
                                                |   SQLite      |
                                                | synchealth.db |
                                                +---------------+
```

Both processes run as separate Docker containers orchestrated by
`docker-compose.yml`. The frontend's nginx config proxies `/api/` to
the backend so CORS is not an issue in production.

## Data model

Five tables, all keyed by `date` (unique constraint) so re-ingestion is
idempotent:

| Table        | Columns                                                  |
|--------------|----------------------------------------------------------|
| weights      | date, weight_kg, source, created_at                      |
| body_fats    | date, body_fat_pct, bmi, source, created_at              |
| heart_rates  | date, resting_hr, source, created_at                     |
| sleeps       | date, total_minutes, deep_minutes, rem_minutes, ...      |
| steps        | date, count, source, created_at                          |

MVP 1.0 writes only to `weights` and `body_fats` from CSV uploads. The
other three tables exist so MVP 1.2 (Garmin) has a place to land.

## API

See `README.md` for the full table. Endpoints are organised by concern:

- `/health` — operational.
- `/ingest/*` — write paths (CSV + JSON), both idempotent.
- `/metrics/*` — read paths that return chart-ready time series.

All endpoints respond with Pydantic v2 models (or plain dicts where the
Pydantic annotation system misbehaves on this Python build — see code
comments in `app/schemas.py`).

## "First-boot degradable" pattern

The same pattern used in `adr-generator` and `buscador-ofertas`:

- The app boots without Zepp or Garmin credentials.
- Settings that don't apply to MVP 1.0 are reserved in `config.py` but
  read as empty strings.
- External integrations are added in later MVPs by filling those
  settings; the boot path never changes.

## Testing

- `backend/tests/test_csv_zepp.py` — 15 tests covering BOM, CRLF,
  shuffled columns, missing columns, range failures, DD/MM fallback,
  Spanish headers, comma decimal (removed), empty input.
- `backend/tests/test_validate.py` — 27 tests covering every range
  boundary, `None` semantics, unknown key, negative values.
- `backend/tests/test_api.py` — 19 tests covering every endpoint, 200
  happy path, 400 empty input, 422 Pydantic validation, idempotency.
- `backend/tests/test_models.py` — 7 tests covering CRUD and unique
  constraints.

Total: 68 tests. Tests use `TestClient` with an isolated SQLite file
under `tmp_path` per test (see `conftest.py`).

## Layout

```
synchealth/
  backend/
    app/
      config.py        pydantic-settings Settings singleton
      db.py            async engine + sessionmaker + create_all
      models.py        SQLAlchemy 2 (mapped_column) models
      schemas.py       Pydantic v2 request/response models
      main.py          FastAPI app + lifespan + endpoints
      ingest/
        __init__.py    placeholder for MVP 1.1 (Zepp API)
        csv_zepp.py    tolerant CSV parser
        validate.py    range validators
      garmin/
        __init__.py    placeholder for MVP 1.2 (Garmin OAuth)
    tests/             pytest suite (68 tests)
    requirements.txt
    Dockerfile         python:3.11-slim-bookworm
  frontend/
    src/
      main.tsx
      App.tsx          3-section layout
      api.ts           typed fetch wrapper
      types.ts         TypeScript interfaces
      styles.css
      components/
        HealthStatus.tsx
        IngestCSV.tsx
        WeightChart.tsx
        MetricsTable.tsx
    nginx.conf         reverse proxy + SPA fallback
    package.json
    tsconfig.json      strict
    vite.config.ts     /api proxy -> :8790
    Dockerfile         node:20-alpine + nginx:1.27-alpine
  docker-compose.yml
  .env.example
  README.md
  docs/architecture.md
```

## Future-proofing

Folders `app/garmin/` and `app/ingest/__init__.py` are reserved as
placeholders so the next MVPs can drop in new modules without touching
the routing or settings layout.