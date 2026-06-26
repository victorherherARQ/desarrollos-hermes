"""FastAPI application for the ADR generator.

Endpoints
---------
    GET  /health     — liveness + model info.
    POST /generate   — generate a MADR 4.0 ADR, commit it on a branch,
                        optionally open a GitHub PR.
    GET  /adrs       — list ADRs already committed to the local repo.

CORS is wide open in dev — the frontend is served on a different
origin (Vite :5173 / nginx :80).

Hardening (rework):
    * Uses the `lifespan` async context manager instead of the
      deprecated `@app.on_event("startup")`.
    * Holds `git_ops._repo_lock` across number + commit so concurrent
      requests can't double-number an ADR.
    * Maps `git_ops.BranchAlreadyExistsError` to HTTP 409 instead of
      silently overwriting the branch.
"""

from __future__ import annotations

import asyncio
import re as _re
from contextlib import asynccontextmanager
from datetime import date
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .git_ops import (
    BranchAlreadyExistsError,
    _repo_lock,
    commit_adr,
    create_pull_request,
    ensure_repo,
    get_next_adr_number,
    list_adrs,
)
from .llm import (
    extract_considered_options,
    extract_pros_cons,
    generate_adr,
    parse_adr_sections,
)
from .madr_template import render_madr
from .models import (
    AdrListResponse,
    AdrRequest,
    AdrResponse,
    HealthResponse,
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Bootstrap the ADR repo on startup using the modern lifespan API.

    Replaces the deprecated `@app.on_event("startup")`. A git error
    during boot is logged but doesn't crash the process — the next
    request will retry `ensure_repo` lazily.
    """
    settings = get_settings()
    try:
        # `ensure_repo` is sync and may touch the FS; offload to a
        # thread so we never block the event loop at boot.
        await asyncio.to_thread(ensure_repo, settings.ADR_REPO_PATH)
    except Exception:  # noqa: BLE001 - don't crash boot on git issues
        # In a real deployment we'd log this; for dev we keep going.
        pass
    yield


app = FastAPI(
    title="ADR Generator",
    description="Generate MADR 4.0 Architecture Decision Records with MiniMax M3.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        model=settings.LLM_MODEL,
        github_enabled=settings.github_enabled,
    )


@app.post("/generate", response_model=AdrResponse)
def generate(req: AdrRequest) -> AdrResponse:
    """Generate an ADR from the form payload, commit it, optionally open a PR."""
    settings = get_settings()

    if not settings.OPENAI_API_KEY:
        raise HTTPException(
            status_code=503,
            detail=(
                "OPENAI_API_KEY is not configured. Set it in "
                "backend/.env or as an environment variable."
            ),
        )

    # 1. LLM emits the body (frontmatter + Markdown).
    form_payload = req.model_dump()
    try:
        body = generate_adr(form_payload)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"LLM call failed: {exc}") from exc

    # 2. Re-render the frontmatter deterministically from the form so we
    #    know exactly what's on disk. The LLM's frontmatter is replaced.
    sections = parse_adr_sections(body)
    form_payload_with_sections = {
        **form_payload,
        "considered_options_markdown": sections.get("Considered Options", ""),
        "pros_cons_markdown": sections.get("Pros and Cons of the Options", ""),
        "decision_outcome": sections.get("Decision Outcome", preliminary_summary(body)),
    }
    if not req.date:
        form_payload_with_sections["date"] = date.today().isoformat()
    rendered = render_madr(form_payload_with_sections)

    # 3. Make sure the frontmatter is the first thing in the file.
    if not rendered.startswith("---"):
        raise HTTPException(
            status_code=500,
            detail="Rendered ADR is missing YAML frontmatter.",
        )

    # 4. Git: ensure repo, compute next number, branch + commit.
    #
    # We hold `_repo_lock` across the number + branch check + commit so
    # two concurrent /generate calls can't produce duplicate numbers or
    # one of them silently reset the other's branch (the C1 race).
    repo = ensure_repo(settings.ADR_REPO_PATH)
    with _repo_lock:
        adr_number = get_next_adr_number(repo)
        filename = f"{adr_number:04d}-{_slug(req.title)}.md"
        try:
            branch, sha = commit_adr(
                repo=repo,
                filename=filename,
                content=rendered,
                adr_number=adr_number,
                title=req.title,
            )
        except BranchAlreadyExistsError as exc:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Branch {exc.branch!r} already exists. Refusing to "
                    "overwrite an existing ADR."
                ),
            ) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=f"Git commit failed: {exc}") from exc

    # 5. Optional GitHub PR. Pushes the branch inside.
    pr_url: Optional[str] = None
    if settings.github_enabled:
        try:
            pr_url = create_pull_request(
                repo=repo,
                branch=branch,
                title=f"ADR {adr_number:04d}: {req.title}",
                body=(
                    f"## {req.title}\n\n"
                    f"{req.context}\n\n"
                    f"**Chosen option:** {req.preliminary_decision}\n"
                ),
            )
        except Exception:  # noqa: BLE001
            pr_url = None

    return AdrResponse(
        adr_number=adr_number,
        filename=filename,
        content=rendered,
        branch=branch,
        commit_sha=sha,
        pr_url=pr_url,
    )


@app.get("/adrs", response_model=AdrListResponse)
def adrs() -> AdrListResponse:
    settings = get_settings()
    repo = ensure_repo(settings.ADR_REPO_PATH)
    return AdrListResponse(adrs=list_adrs(repo))


# ---------------------------------------------------------------------------
# Local helpers
# ---------------------------------------------------------------------------


def _slug(text: str, max_len: int = 60) -> str:
    s = text.lower()
    s = _re.sub(r"[^a-z0-9\s-]", "", s)
    s = _re.sub(r"\s+", "-", s).strip("-")
    return s[:max_len] or "adr"


def preliminary_summary(body: str) -> str:
    """Return the first non-empty paragraph after the H1, used as the
    default `decision_outcome` when the LLM doesn't emit one explicitly."""
    lines = body.splitlines()
    in_body = False
    para: list[str] = []
    for line in lines:
        if not in_body:
            if line.startswith("# "):
                in_body = True
                continue
        else:
            if line.startswith("## "):
                break
            if line.strip():
                para.append(line.strip())
    return " ".join(para).strip() or "See Context and Problem Statement."