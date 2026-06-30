"""SQLAlchemy models for synchealth.

Five biometric series, each keyed by `date` with a `unique` constraint
so re-ingesting the same day is idempotent (the row gets updated, not
duplicated).

MVP 1.0 only writes to `Weight` and `BodyFat` from CSV uploads. The
other three tables exist so MVP 1.2 (Garmin) has a place to land.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for all synchealth models."""


class Weight(Base):
    __tablename__ = "weights"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, unique=True, index=True)
    weight_kg: Mapped[float] = mapped_column(Float, nullable=False)  # 30..200
    source: Mapped[str] = mapped_column(String, default="zepp_csv")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class BodyFat(Base):
    __tablename__ = "body_fats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, unique=True, index=True)
    body_fat_pct: Mapped[float] = mapped_column(Float, nullable=False)  # 3..70
    bmi: Mapped[float | None] = mapped_column(Float, nullable=True)  # 10..60
    source: Mapped[str] = mapped_column(String, default="zepp_csv")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class HeartRate(Base):
    __tablename__ = "heart_rates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, unique=True, index=True)
    resting_hr: Mapped[int] = mapped_column(Integer, nullable=False)  # 30..120
    source: Mapped[str] = mapped_column(String, default="garmin_export")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Sleep(Base):
    __tablename__ = "sleeps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, unique=True, index=True)
    total_minutes: Mapped[int] = mapped_column(Integer, nullable=False)  # 0..1440
    deep_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rem_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String, default="garmin_export")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Steps(Base):
    __tablename__ = "steps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, unique=True, index=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False)  # 0..100000
    source: Mapped[str] = mapped_column(String, default="garmin_export")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)