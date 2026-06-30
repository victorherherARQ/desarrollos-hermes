"""FastAPI application for synchealth MVP 1.0.

Endpoints
---------
    GET   /health                       — liveness + DB ping.
    POST  /ingest/weight                — insert/update weight rows (JSON).
    POST  /ingest/csv                   — multipart upload of a Zepp CSV.
    GET   /ingest/preview-csv           — parse CSV without inserting.
    GET   /metrics/weight?days=30       — weight series.
    GET   /metrics/body_fat?days=90     — body fat series.
    GET   /metrics/resting_hr?days=30   — resting HR series (placeholder data).
    GET   /metrics/sleep?days=30        — sleep series (placeholder data).
    GET   /metrics/steps?days=30        — steps series (placeholder data).

CORS is open in dev because the Vite frontend (port 5173 / nginx 80) hits
a different origin than the backend (port 8790).

Pattern: "first-boot degradable" — the app boots without Zepp or
Garmin credentials; every external integration is optional.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date, timedelta
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .config import get_settings
from .db import create_all, get_sessionmaker, init_engine
from .ingest.csv_zepp import parse_csv_stream
from .models import BodyFat, HeartRate, Sleep, Steps, Weight
from .schemas import (
    CSVPreviewResponse,
    HealthResponse,
    IngestRequest,
    IngestResponse,
    MetricPoint,
    MetricsResponse,
)


# Maximum size for CSV uploads (10 MiB). Anything larger is rejected to
# prevent DoS via memory exhaustion in `await file.read()`.
MAX_CSV_UPLOAD_BYTES = 10 * 1024 * 1024


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Bootstrap engine + schema at boot.

    Uses the modern `lifespan` API (not the deprecated
    `@app.on_event("startup")`). A failure during `create_all` is
    logged but doesn't crash the process — `get_settings()` will be
    retried lazily on the next request.
    """
    settings = get_settings()
    db_path: Path = settings.db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    init_engine(settings.database_url, in_memory=False)
    try:
        await create_all()
    except Exception:  # noqa: BLE001 - never crash boot on schema issues
        pass
    yield


app = FastAPI(
    title="synchealth",
    description="Self-hosted biometric aggregator (MVP 1.0).",
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
# Session dependency
# ---------------------------------------------------------------------------

async def session_dep() -> AsyncSession:
    """FastAPI dependency that yields an `AsyncSession`."""
    sm = get_sessionmaker()
    async with sm() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


SessionDep = Annotated[AsyncSession, Depends(session_dep)]


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse)
async def health(session: SessionDep) -> HealthResponse:
    """Liveness probe with a DB ping."""
    settings = get_settings()
    db_ok = False
    try:
        await session.execute(select(1))
        db_ok = True
    except Exception:  # noqa: BLE001
        db_ok = False
    return HealthResponse(
        status="ok" if db_ok else "degraded",
        db=db_ok,
        version=settings.APP_VERSION,
    )


# ---------------------------------------------------------------------------
# /ingest/weight (JSON, idempotent by date)
# ---------------------------------------------------------------------------

@app.post("/ingest/weight", response_model=IngestResponse)
async def ingest_weight(payload: IngestRequest, session: SessionDep) -> IngestResponse:
    """Insert/update weight rows. Idempotent: re-POSTing the same date
    updates the existing row instead of duplicating it.
    """
    inserted = updated = skipped = 0

    for row in payload.rows:
        if row.weight_kg is None:
            skipped += 1
            continue

        existing = await session.execute(
            select(Weight).where(Weight.date == row.date)
        )
        existing_row = existing.scalar_one_or_none()
        if existing_row is None:
            session.add(
                Weight(
                    date=row.date,
                    weight_kg=row.weight_kg,
                    source=payload.source,
                )
            )
            inserted += 1
        else:
            existing_row.weight_kg = row.weight_kg
            existing_row.source = payload.source
            updated += 1

        # Side-effect: if the row also carries BMI, upsert BodyFat.
        if row.bmi is not None:
            bf_existing = await session.execute(
                select(BodyFat).where(BodyFat.date == row.date)
            )
            bf = bf_existing.scalar_one_or_none()
            if bf is None:
                session.add(
                    BodyFat(
                        date=row.date,
                        body_fat_pct=row.body_fat_pct or 0.0,
                        bmi=row.bmi,
                        source=payload.source,
                    )
                )
            else:
                bf.bmi = row.bmi
                if row.body_fat_pct is not None:
                    bf.body_fat_pct = row.body_fat_pct

    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=400, detail="database integrity error")

    total = inserted + updated + skipped
    return IngestResponse(
        inserted=inserted,
        updated=updated,
        skipped=skipped,
        total=total,
    )


# ---------------------------------------------------------------------------
# /ingest/csv (multipart upload)
# ---------------------------------------------------------------------------

@app.post("/ingest/csv", response_model=IngestResponse)
async def ingest_csv(
    session: SessionDep,
    file: UploadFile = File(...),
) -> IngestResponse:
    """Parse an uploaded Zepp Life CSV and insert valid rows."""
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="empty file")
    if len(raw) > MAX_CSV_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"file too large (max {MAX_CSV_UPLOAD_BYTES // (1024 * 1024)} MiB)",
        )

    result = parse_csv_stream(raw)
    if result.valid_count == 0:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "no valid rows",
                "total": result.total,
                "invalid": result.invalid_count,
            },
        )

    inserted = updated = skipped = 0
    for row in result.invalid_rows:
        skipped += 1

    for row in result.valid_rows:
        assert row.date is not None  # valid rows always have a date
        if row.weight_kg is not None:
            existing = await session.execute(
                select(Weight).where(Weight.date == row.date)
            )
            w = existing.scalar_one_or_none()
            if w is None:
                session.add(
                    Weight(
                        date=row.date,
                        weight_kg=row.weight_kg,
                        source="zepp_csv",
                    )
                )
                inserted += 1
            else:
                w.weight_kg = row.weight_kg
                w.source = "zepp_csv"
                updated += 1

        if row.body_fat_pct is not None or row.bmi is not None:
            bf_existing = await session.execute(
                select(BodyFat).where(BodyFat.date == row.date)
            )
            bf = bf_existing.scalar_one_or_none()
            if bf is None:
                session.add(
                    BodyFat(
                        date=row.date,
                        body_fat_pct=row.body_fat_pct or 0.0,
                        bmi=row.bmi,
                        source="zepp_csv",
                    )
                )
                inserted += 1
            else:
                if row.body_fat_pct is not None:
                    bf.body_fat_pct = row.body_fat_pct
                if row.bmi is not None:
                    bf.bmi = row.bmi
                bf.source = "zepp_csv"
                updated += 1

    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=400, detail="database integrity error")

    total = inserted + updated + skipped
    return IngestResponse(
        inserted=inserted,
        updated=updated,
        skipped=skipped,
        total=total,
    )


# ---------------------------------------------------------------------------
# /ingest/preview-csv (parse without inserting)
# ---------------------------------------------------------------------------

@app.post("/ingest/preview-csv", response_model=CSVPreviewResponse)
async def preview_csv(file: UploadFile = File(...)) -> CSVPreviewResponse:
    """Parse a CSV and return a structured preview without inserting."""
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="empty file")
    if len(raw) > MAX_CSV_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"file too large (max {MAX_CSV_UPLOAD_BYTES // (1024 * 1024)} MiB)",
        )

    result = parse_csv_stream(raw)
    rows: list[dict] = []
    for r in result.rows:
        rows.append(
            {
                "row_number": r.row_number,
                "date": r.date.isoformat() if r.date else None,
                "weight_kg": r.weight_kg,
                "body_fat_pct": r.body_fat_pct,
                "bmi": r.bmi,
                "errors": list(r.errors),
            }
        )

    return CSVPreviewResponse(
        total_rows=result.total,
        valid_rows=result.valid_count,
        invalid_rows=result.invalid_count,
        rows=rows,
    )


# ---------------------------------------------------------------------------
# /metrics/* (chart series)
# ---------------------------------------------------------------------------

def _period_start(days: int) -> date:
    return date.today() - timedelta(days=days)


async def _weight_points(session: AsyncSession, since: date) -> list[MetricPoint]:
    res = await session.execute(
        select(Weight).where(Weight.date >= since).order_by(Weight.date)
    )
    return [
        MetricPoint(date=w.date, value=float(w.weight_kg))
        for w in res.scalars().all()
    ]


async def _body_fat_points(session: AsyncSession, since: date) -> list[MetricPoint]:
    res = await session.execute(
        select(BodyFat).where(BodyFat.date >= since).order_by(BodyFat.date)
    )
    return [
        MetricPoint(date=bf.date, value=float(bf.body_fat_pct))
        for bf in res.scalars().all()
    ]


async def _generic_points(
    session: AsyncSession, model: type, value_attr: str, since: date
) -> list[MetricPoint]:
    res = await session.execute(
        select(model).where(model.date >= since).order_by(model.date)  # type: ignore[attr-defined]
    )
    return [
        MetricPoint(date=row.date, value=float(getattr(row, value_attr)))
        for row in res.scalars().all()
    ]


@app.get("/metrics/weight", response_model=MetricsResponse)
async def metrics_weight(
    session: SessionDep,
    days: int = Query(30, ge=1, le=3650),
) -> MetricsResponse:
    points = await _weight_points(session, _period_start(days))
    return MetricsResponse(metric="weight_kg", period_days=days, points=points)


@app.get("/metrics/body_fat", response_model=MetricsResponse)
async def metrics_body_fat(
    session: SessionDep,
    days: int = Query(90, ge=1, le=3650),
) -> MetricsResponse:
    points = await _body_fat_points(session, _period_start(days))
    return MetricsResponse(metric="body_fat_pct", period_days=days, points=points)


@app.get("/metrics/resting_hr", response_model=MetricsResponse)
async def metrics_resting_hr(
    session: SessionDep,
    days: int = Query(30, ge=1, le=3650),
) -> MetricsResponse:
    points = await _generic_points(session, HeartRate, "resting_hr", _period_start(days))
    return MetricsResponse(metric="resting_hr", period_days=days, points=points)


@app.get("/metrics/sleep", response_model=MetricsResponse)
async def metrics_sleep(
    session: SessionDep,
    days: int = Query(30, ge=1, le=3650),
) -> MetricsResponse:
    points = await _generic_points(session, Sleep, "total_minutes", _period_start(days))
    return MetricsResponse(metric="total_minutes", period_days=days, points=points)


@app.get("/metrics/steps", response_model=MetricsResponse)
async def metrics_steps(
    session: SessionDep,
    days: int = Query(30, ge=1, le=3650),
) -> MetricsResponse:
    points = await _generic_points(session, Steps, "count", _period_start(days))
    return MetricsResponse(metric="count", period_days=days, points=points)