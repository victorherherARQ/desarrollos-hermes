# ADR Generator — Architecture

## Overview

`adr-generator` is a small two-tier web app:

* **Frontend** — React + Vite + TypeScript single-page app that renders
  a structured form and a live Markdown preview.
* **Backend** — FastAPI service that owns the LLM call, the MADR 4.0
  template, the Git repo lifecycle, and the (optional) GitHub PR.

The LLM is reached over an **OpenAI-compatible HTTPS endpoint** (the
backend's `OPENAI_BASE_URL` defaults to `https://api.minimax.io/v1`),
which means we can use the standard `openai` Python SDK against the
**MiniMax M3** model without any custom protocol work.

## End-to-end flow

```
                  ┌────────────────────────┐
                  │  Browser (React form)  │
                  └────────────┬───────────┘
                               │ POST /generate
                               ▼
                  ┌────────────────────────┐
                  │   FastAPI backend      │
                  └────────────┬───────────┘
                               │
        ┌──────────────────────┼──────────────────────┐
        ▼                      ▼                      ▼
 ┌──────────────┐       ┌──────────────┐       ┌──────────────┐
 │   LLM call   │       │ MADR check   │       │  Git ops     │
 │ MiniMax M3   │       │ frontmatter  │       │ commit + push│
 │ (OpenAI-     │       │ --- ... ---  │       │ docs/adr/... │
 │  compat)     │       │ + secciones  │       │ adr/NNN-slug │
 └──────┬───────┘       └──────┬───────┘       └──────┬───────┘
        │                      │                      │
        ▼                      ▼                      ▼
 ┌──────────────┐       ┌──────────────┐       ┌──────────────┐
 │ Markdown     │       │ Rendered     │       │  GitHub API  │
 │ body (LLM)   │ ────▶ │ ADR text     │ ────▶ │  PR create   │
 └──────────────┘       └──────────────┘       └──────────────┘
```

## Step-by-step

1. **Submit** — Browser sends `POST /generate` with `AdrRequest`.
2. **LLM** — Backend calls `client.chat.completions.create(...)` with
   the `SYSTEM_PROMPT` (MADR 4.0 enforcement + few-shot example) and
   the form payload as a JSON user message. Model: **MiniMax M3**.
3. **MADR check** — `madr_template.render_madr` rebuilds the frontmatter
   from the structured request so the YAML at the top of the file is
   always predictable. The LLM's `## Considered Options` and
   `## Pros and Cons of the Options` sections are spliced in if the
   model emitted them.
4. **Git ops** — `ensure_repo` initialises the local repo on first run
   (creates `docs/adr/.gitkeep`, makes the bootstrap commit).
   `get_next_adr_number` reads the highest `NNNN-*.md` filename and
   increments. `commit_adr` checks out a fresh `adr/NNNN-slug` branch,
   writes the file, and commits it. The commit SHA is returned.
5. **GitHub** — If `GITHUB_TOKEN` and `GITHUB_REPO` are set,
   `create_pull_request` posts to `https://api.github.com/repos/{owner}/{repo}/pulls`.
6. **Response** — The backend returns the rendered content plus the
   branch, commit SHA, and (if available) the PR URL. The UI shows
   the Markdown rendered with `react-markdown` and offers Copy /
   Download buttons.

## State & storage

* **ADR repo** lives at `ADR_REPO_PATH` (default `/tmp/adr-test-repo`
  in dev, `/app/data` in Docker). Mounted as the `adr-data` named
  volume in compose.
* **No database.** The repo *is* the source of truth for ADRs.
* **No long-running process.** `uvicorn app.main:app` is the only
  service; the Git repo is the durable state.

## Why MADR 4.0?

MADR's frontmatter is machine-readable, its section list is small and
unambiguous, and the "Bueno/Malo, porque…" pattern keeps pros & cons
factual and brief. See https://adr.github.io/madr/ for the spec.

## Security notes

* Secrets live only in `backend/.env` (or the compose `env_file`).
  Never hard-coded.
* The LLM is **only ever called server-side** — the browser never
  sees the API key.
* CORS is wide open in dev for convenience; production deployments
  should lock `allow_origins` down to the actual frontend host.
* The GitHub token uses the standard `Bearer` Authorization header
  and is sent only when opening a PR.