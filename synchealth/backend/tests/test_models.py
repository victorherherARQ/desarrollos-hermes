"""Tests for the SQLAlchemy models (CRUD + unique constraint)."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BodyFat, Weight


# ---------------------------------------------------------------------------
# Weight CRUD
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_weight_insert_and_fetch(session: AsyncSession):
    w = Weight(date=date(2025, 5, 1), weight_kg=89.4, source="manual")
    session.add(w)
    await session.commit()
    await session.refresh(w)
    assert w.id is not None
    assert w.weight_kg == 89.4


@pytest.mark.asyncio
async def test_weight_unique_constraint_on_date(session: AsyncSession):
    session.add(Weight(date=date(2025, 5, 1), weight_kg=89.4))
    await session.commit()

    session.add(Weight(date=date(2025, 5, 1), weight_kg=90.0))
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()


@pytest.mark.asyncio
async def test_weight_update_existing(session: AsyncSession):
    session.add(Weight(date=date(2025, 5, 1), weight_kg=89.4))
    await session.commit()

    from sqlalchemy import select

    res = await session.execute(select(Weight).where(Weight.date == date(2025, 5, 1)))
    w = res.scalar_one()
    w.weight_kg = 90.0
    await session.commit()

    res = await session.execute(select(Weight).where(Weight.date == date(2025, 5, 1)))
    assert res.scalar_one().weight_kg == 90.0


@pytest.mark.asyncio
async def test_weight_delete(session: AsyncSession):
    from sqlalchemy import select

    session.add(Weight(date=date(2025, 5, 1), weight_kg=89.4))
    await session.commit()

    res = await session.execute(select(Weight).where(Weight.date == date(2025, 5, 1)))
    w = res.scalar_one()
    await session.delete(w)
    await session.commit()

    res = await session.execute(select(Weight))
    assert res.scalars().all() == []


# ---------------------------------------------------------------------------
# BodyFat CRUD
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_body_fat_insert_optional_bmi(session: AsyncSession):
    bf = BodyFat(
        date=date(2025, 5, 1),
        body_fat_pct=25.2,
        bmi=None,
        source="manual",
    )
    session.add(bf)
    await session.commit()
    await session.refresh(bf)
    assert bf.bmi is None
    assert bf.body_fat_pct == 25.2


@pytest.mark.asyncio
async def test_body_fat_unique_constraint(session: AsyncSession):
    session.add(BodyFat(date=date(2025, 5, 1), body_fat_pct=25.2))
    await session.commit()

    session.add(BodyFat(date=date(2025, 5, 1), body_fat_pct=24.0))
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()


@pytest.mark.asyncio
async def test_pagination_simple(session: AsyncSession):
    """Insert N rows and verify ordered fetch returns them in order."""
    from sqlalchemy import select

    for i in range(5):
        session.add(Weight(date=date(2025, 5, i + 1), weight_kg=89.0 - i * 0.1))
    await session.commit()

    res = await session.execute(select(Weight).order_by(Weight.date).limit(3))
    rows = res.scalars().all()
    assert len(rows) == 3
    assert rows[0].date == date(2025, 5, 1)
    assert rows[2].date == date(2025, 5, 3)