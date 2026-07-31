"""Descargador de CSVs de football-data.co.uk para LaLiga 1ª y 2ª.

football-data.co.uk mantiene CSVs por temporada y división. La URL tiene
el patrón:

    https://www.football-data.co.uk/mmz4281/{season_short}/{div}.csv

donde:
    * ``season_short`` = ``2526`` para 2025-26, ``2425`` para 2024-25, etc.
    * ``div`` = ``SP1`` (LaLiga 1ª), ``SP2`` (LaLiga 2ª / SmartBank)

Columnas de interés en el CSV (nombres reales verificados):
    * ``Date`` — fecha del partido (formato dd/mm/yyyy)
    * ``HomeTeam``, ``AwayTeam`` — nombres canónicos
    * ``FTHG``, ``FTAG`` — goles final (Full Time Home / Away Goals)
    * ``FTR`` — resultado final (``H`` / ``D`` / ``A``)
    * ``MW`` — MatchWeek (jornada de liga 1..38)

Otras columnas (xG, tiros, corners) existen pero son de pago. Las
ignoramos en MVP 1.0.
"""
from __future__ import annotations

import csv
import io
import logging
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import httpx

from ..db.repository import init_schema, upsert_match

log = logging.getLogger(__name__)

BASE_URL = "https://www.football-data.co.uk/mmz4281/{season}/{div}.csv"

# Divisions we care about. SP1 = LaLiga 1ª, SP2 = LaLiga 2ª.
DIVISIONS = ("SP1", "SP2")


@dataclass
class SeasonSpec:
    season: str         # '2526'
    start_year: int     # 2025
    end_year: int       # 2026


def default_seasons() -> list[SeasonSpec]:
    """Seasons to download. 2025-26 is the current one; the user asked
    for the whole season, so we pull everything since 2010-11 (15
    seasons of data → enough for Dixon-Coles fitting without overfitting
    on defunct teams).

    The football-data.co.uk URL slug is ``2526`` for 2025-26 — i.e. the
    last two digits of each year concatenated.
    """
    return [
        SeasonSpec(f"{str(y)[-2:]}{str(y + 1)[-2:]}", y, y + 1)
        for y in range(2010, 2026)  # 2010..2025 inclusive
    ]


def parse_match_date(s: str) -> date | None:
    """Parse football-data.co.uk's dd/mm/yyyy (or dd/mm/yy) format."""
    s = s.strip()
    if not s:
        return None
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def parse_int_safe(s: str | None) -> int | None:
    if s is None:
        return None
    s = s.strip()
    if not s:
        return None
    try:
        return int(s)
    except ValueError:
        return None


def download_season_csv(
    season: str, division: str, *, client: httpx.Client | None = None
) -> str:
    """Return the raw CSV text for one season + division. Raises on
    HTTP errors."""
    url = BASE_URL.format(season=season, div=division)
    owns_client = client is None
    client = client or httpx.Client(timeout=30.0, headers={
        "User-Agent": "quiniela-analyzer/0.1 (personal project)"
    })
    try:
        resp = client.get(url)
        resp.raise_for_status()
        return resp.text
    finally:
        if owns_client:
            client.close()


def ingest_season(
    season: str, division: str, csv_text: str, *, conn: sqlite3.Connection
) -> tuple[int, int]:
    """Insert matches from one CSV. Returns (inserted, skipped)."""
    inserted = 0
    skipped = 0
    reader = csv.DictReader(io.StringIO(csv_text))
    for row in reader:
        match_date = parse_match_date(row.get("Date", ""))
        if match_date is None:
            skipped += 1
            continue
        jornada_raw = row.get("MW") or row.get("MatchWeek") or "0"
        try:
            jornada = int(float(jornada_raw))
        except (ValueError, TypeError):
            jornada = 0
        home_team = (row.get("HomeTeam") or "").strip()
        away_team = (row.get("AwayTeam") or "").strip()
        if not home_team or not away_team:
            skipped += 1
            continue

        # Filter out future matches (no result yet).
        if match_date > date.today():
            skipped += 1
            continue

        home_goals = parse_int_safe(row.get("FTHG"))
        away_goals = parse_int_safe(row.get("FTAG"))
        if home_goals is None or away_goals is None:
            skipped += 1
            continue

        upsert_match(
            conn,
            season=season,
            division=division,
            jornada=jornada,
            matchday_date=match_date,
            home_team=home_team,
            away_team=away_team,
            home_goals=home_goals,
            away_goals=away_goals,
            source=f"football-data.co.uk:{season}:{division}",
        )
        inserted += 1
    return inserted, skipped


def run_historico(
    seasons: list[SeasonSpec] | None = None,
    divisions: tuple[str, ...] = DIVISIONS,
    db_path: Path | str | None = None,
) -> dict[str, dict[str, tuple[int, int]]]:
    """Download + ingest all seasons. Returns nested dict of counts."""
    seasons = seasons or default_seasons()
    init_schema(db_path)
    results: dict[str, dict[str, tuple[int, int]]] = {}
    from ..db.repository import get_connection
    with httpx.Client(timeout=30.0, headers={
        "User-Agent": "quiniela-analyzer/0.1 (personal project)"
    }) as client:
        for spec in seasons:
            results[spec.season] = {}
            for div in divisions:
                try:
                    csv_text = download_season_csv(spec.season, div, client=client)
                except httpx.HTTPStatusError as e:
                    log.warning("HTTP %s fetching %s/%s", e.response.status_code, spec.season, div)
                    results[spec.season][div] = (0, 0)
                    continue
                with get_connection(db_path) as conn:
                    ins, skp = ingest_season(spec.season, div, csv_text, conn=conn)
                results[spec.season][div] = (ins, skp)
                log.info("%s/%s: inserted=%d skipped=%d", spec.season, div, ins, skp)
    return results