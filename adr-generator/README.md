# ADR Generator

A small web app that turns a structured form into a fully-formed
**Architecture Decision Record (ADR)** in the **MADR 4.0** format using
the MiniMax M3 LLM. The result is rendered as Markdown in the UI,
downloaded as a `.md` file, committed to a local Git repository on a
dedicated `adr/NNN-slug` branch, and — when a GitHub token is set —
pushed as a Pull Request.

## Stack

| Layer       | Tech                                       | Version |
|-------------|--------------------------------------------|---------|
| Backend     | FastAPI + Uvicorn                          | 0.115 / 0.32 |
| Backend     | Pydantic / pydantic-settings               | 2.9.2 / 2.6.0 |
| Backend     | OpenAI SDK (compatible w/ MiniMax M3)      | 1.54.0 |
| Backend     | httpx / GitPython                          | 0.27.2 / 3.1.43 |
| Frontend    | React + Vite + TypeScript                  | 18.3 / 5.4 / 5.6 |
| Frontend    | axios / react-markdown                     | 1.7.7 / 9.0.1 |
| Tests       | pytest / pytest-asyncio                    | 8.3.3 / 0.24.0 |
| Containers  | Docker / docker-compose                    | n/a |

## Prerequisites

- Docker + Docker Compose (the simplest path).
- An **OpenAI-compatible API key** for MiniMax M3. Set it via `OPENAI_API_KEY`.
- *(Optional)* A `GITHUB_TOKEN` + `GITHUB_REPO` (in `owner/repo` form) to enable
  Pull Request creation after a successful commit.

## Installation

```bash
git clone <this-repo>
cd adr-generator

# Backend env — fill in your key
cp backend/.env.example backend/.env
$EDITOR backend/.env

# Frontend env — defaults are fine for local dev
cp frontend/.env.example frontend/.env

# Boot everything
docker compose up -d --build
```

## URLs

| Service        | URL                                |
|----------------|------------------------------------|
| Frontend (UI)  | http://localhost:5173              |
| Backend (API)  | http://localhost:8000              |
| API docs (Swagger) | http://localhost:8000/docs      |
| OpenAPI schema | http://localhost:8000/openapi.json |

## UI Walkthrough (ASCII)

```
┌──────────────────────────────┐    ┌────────────────────────────────────┐
│  Formulario                  │    │  Resultado                         │
│ ─────────────────────────    │    │  ─────────────────────────────     │
│  Título: [____________]      │    │  #0001 use-postgresql-as-primary   │
│  Contexto:                   │ →  │                                    │
│  [____________________]      │    │  ## Context and Problem Statement  │
│  Tecnologías: [_____]        │    │  We need a transactional…           │
│  Decisión: [_________]       │    │                                    │
│  Opciones:  [_________]      │    │  ## Decision Outcome                │
│  Estado:    [proposed ▼]     │    │  Chosen option: "PostgreSQL"…      │
│                              │    │                                    │
│  [ Generar ADR ]  [ Limpiar ]│    │  [ Copiar Markdown ] [ Descargar ] │
└──────────────────────────────┘    └────────────────────────────────────┘
```

## API endpoints

### `GET /health`

```bash
curl http://localhost:8000/health
# {"status":"ok","model":"MiniMax-M3","github_enabled":false}
```

### `POST /generate`

```bash
curl -X POST http://localhost:8000/generate \
  -H 'Content-Type: application/json' \
  -d '{
    "title": "Use PostgreSQL as primary database",
    "context": "We need a transactional relational database that supports JSON and full-text search.",
    "technologies": ["PostgreSQL", "Python"],
    "preliminary_decision": "Managed PostgreSQL (RDS / Cloud SQL)",
    "options_to_evaluate": ["Managed PostgreSQL", "MySQL 8", "CockroachDB"],
    "status": "accepted"
  }'
```

Response:

```json
{
  "adr_number": 1,
  "filename": "0001-use-postgresql-as-primary-database.md",
  "content": "---\ntitle: ...\n---\n# Use PostgreSQL...",
  "branch": "adr/0001-use-postgresql-as-primary-database",
  "commit_sha": "f0e1d2c3b4a5...",
  "pr_url": null
}
```

### `GET /adrs`

Lists the ADRs already committed to the local repo.

```bash
curl http://localhost:8000/adrs
# {"adrs":[{"number":1,"filename":"0001-...md","status":"accepted","title":"..."}]}
```

## How it works

1. The browser submits the form to `POST /generate`.
2. The FastAPI backend calls MiniMax M3 (OpenAI-compatible) with a
   system prompt that enforces MADR 4.0 structure and the
   "Bueno, porque / Malo, porque" pros-and-cons pattern.
3. The LLM body is rendered into the exact MADR 4.0 template by
   `madr_template.render_madr`, which **rebuilds the YAML frontmatter
   deterministically** from the request — so the file on disk always
   matches the form fields.
4. The file is written to `docs/adr/NNNN-slug.md`, committed on a
   fresh `adr/NNNN-slug` branch, and (if `GITHUB_TOKEN` + `GITHUB_REPO`
   are set) a PR is opened via the GitHub REST API.

See `docs/architecture.md` for the flow diagram.

## Development

```bash
# Backend — tests
cd backend
pip install -r requirements.txt
PYTHONPATH=. pytest tests/ -v

# Backend — run locally
PYTHONPATH=. uvicorn app.main:app --reload --port 8000

# Frontend — dev server
cd ../frontend
npm install
npm run dev      # http://localhost:5173
npm run typecheck
npm run build
```

## Project structure

```
adr-generator/
├── backend/           # FastAPI app + tests
├── frontend/          # React + Vite + TS
├── docs/              # Architecture documentation
├── docker-compose.yml # Local stack
├── .env.example       # Top-level env vars
└── README.md
```

## Contributing

1. Fork & create a feature branch.
2. Add/adjust tests in `backend/tests/`.
3. Run the full test suite (`pytest backend/tests/ -v`) and ensure
   `tsc --noEmit` is green on the frontend.
4. Open a PR. Conventional commits preferred (`feat:`, `fix:`, `docs:`).

## License

MIT — see `LICENSE` if present, otherwise all rights reserved by the
author until a `LICENSE` file is added.

## Author

Victor (vhdez) — 2026.