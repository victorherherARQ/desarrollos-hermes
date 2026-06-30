# synchealth

Self-hosted biometric aggregator for **Garmin Connect** and **Zepp Life** data.

## MVP 1.0 (this release)

The first milestone ships only the foundation:

- FastAPI 0.115 backend on Python 3.11 + SQLAlchemy 2 (async) + SQLite.
- Five biometric tables (`weights`, `body_fats`, `heart_rates`, `sleeps`, `steps`) keyed by `date`.
- Two ingestion paths: direct JSON `POST /ingest/weight` and CSV upload `POST /ingest/csv` (Zepp Life format).
- Five read endpoints `GET /metrics/*` that return chart-ready series.
- React 18 + Vite + TypeScript + recharts frontend, three sections (banner, ingest, metrics).
- Docker + docker-compose for the whole stack.
- 68 passing pytest tests.

MVP 1.0 does **NOT** integrate with Zepp or Garmin yet. Those arrive in later MVPs.

## Quick start (Docker)

```bash
cp .env.example .env
docker compose up --build
# Backend: http://localhost:8790/health
# Frontend: http://localhost:5190
```

## Quick start (local dev)

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8790
```

### Frontend

```bash
cd frontend
npm install
npm run dev   # http://localhost:5173, proxies /api -> :8790
```

### Tests

```bash
cd backend && source .venv/bin/activate && pytest -v
cd frontend && npm run build    # tsc + vite build
```

## CSV format (Zepp Life export)

```
Date,Weight (kg),BMI,Body Fat (%),Muscle Mass (kg),Body Water (%),Bone Mass (kg),Visceral Fat,Basal Metabolism (kcal)
2025-05-01,89.4,28.5,25.2,55.8,55.0,3.6,11.2,1820
```

The parser tolerates UTF-8 BOM, CRLF endings, shuffled column order, missing columns and Spanish headers (`Fecha`, `Peso (kg)`, `IMC`, `Grasa Corporal (%)`). Out-of-range values are silently dropped, not rejected.

## Endpoints

| Method | Path                    | Description                                    |
|--------|-------------------------|------------------------------------------------|
| GET    | `/health`               | Liveness + DB ping                             |
| POST   | `/ingest/weight`        | Insert/update weight rows (JSON, idempotent)   |
| POST   | `/ingest/csv`           | Multipart upload of a Zepp CSV                 |
| POST   | `/ingest/preview-csv`   | Parse CSV without inserting                    |
| GET    | `/metrics/weight?days=N`| Weight series (kg)                             |
| GET    | `/metrics/body_fat?days=N` | Body-fat series (%)                         |
| GET    | `/metrics/resting_hr?days=N` | Resting heart-rate (placeholder, MVP 1.2)  |
| GET    | `/metrics/sleep?days=N` | Sleep minutes (placeholder, MVP 1.2)           |
| GET    | `/metrics/steps?days=N` | Step count (placeholder, MVP 1.2)              |

## Próximos MVPs

- **1.1** — Zepp Life API client (`backend/app/zepp/` — folder reserved in `app/ingest/__init__.py`), automatic daily pull.
- **1.2** — Garmin Connect OAuth + read APIs (folder reserved in `backend/app/garmin/`).
- **1.3** — Cron job that runs the daily pipeline and posts a Telegram summary.
- **2.x** — Train/nutrition recommendations over the consolidated dataset.