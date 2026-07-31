"""Team value features: budget, market value, squad size from Wikipedia.

This module extracts financial and structural data for La Liga teams
and stores it in the `team_features` SQLite table.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from .wiki_parser import (
    TeamWikiData,
    scrape_all_teams,
    save_cache,
    load_cache,
)

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "quiniela.db"
CACHE_PATH = Path(__file__).resolve().parents[2] / "data" / "raw" / "team_features_seed.json"

# La Liga 2025-26 teams (20 teams)
LALIGA_2526_TEAMS = [
    "Real Madrid", "Barcelona", "Girona", "Atlético Madrid",
    "Athletic Bilbao", "Real Sociedad", "Real Betis", "Sevilla",
    "Villarreal", "Valencia", "Getafe", "Osasuna", "Celta Vigo",
    "Mallorca", "Espanyol", "Leganés", "Alavés", "Rayo Vallecano",
    "Real Valladolid", "Las Palmas",
]

# Segunda División 2025-26 teams (top ones for now)
SEGUNDA_2526_TEAMS = [
    "Levante", "Espanyol", "Real Valladolid", "Elche",
    "Burgos", "Albacete", "Córdoba", "Huesca",
    " Racing Santander", "Tenerife",
]


def get_schema() -> str:
    return """
    CREATE TABLE IF NOT EXISTS team_features (
        team_id       TEXT NOT NULL,
        season        TEXT NOT NULL,
        manager       TEXT,
        captain       TEXT,
        stadium       TEXT,
        stadium_capacity INTEGER,
        kit_brand     TEXT,
        squad_size    INTEGER,
        budget_millions REAL,
        market_value_millions REAL,
        source        TEXT,
        scraped_at    TEXT,
        imputed       INTEGER DEFAULT 0,
        PRIMARY KEY (team_id, season)
    );
    """


def init_team_features(conn: sqlite3.Connection) -> None:
    """Create team_features table if not exists."""
    conn.execute(get_schema())


def upsert_team_features(conn: sqlite3.Connection, data: TeamWikiData, imputed: bool = False) -> None:
    """Insert or update a team_features row."""
    now = datetime.utcnow().isoformat()
    conn.execute(
        """
        INSERT INTO team_features(
            team_id, season, manager, captain, stadium, stadium_capacity,
            kit_brand, squad_size, budget_millions, market_value_millions,
            source, scraped_at, imputed
        )
        VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(team_id, season) DO UPDATE SET
            manager = excluded.manager,
            captain = excluded.captain,
            stadium = excluded.stadium,
            stadium_capacity = excluded.stadium_capacity,
            kit_brand = excluded.kit_brand,
            squad_size = excluded.squad_size,
            budget_millions = excluded.budget_millions,
            market_value_millions = excluded.market_value_millions,
            source = excluded.source,
            scraped_at = excluded.scraped_at,
            imputed = excluded.imputed
        """,
        (
            data.team_id,
            data.season,
            data.manager,
            data.captain,
            data.stadium,
            data.stadium_capacity,
            data.kit_brand,
            data.squad_size,
            data.budget_millions,
            data.market_value_millions,
            data.source_url,
            data.scraped_at or now,
            1 if imputed else 0,
        ),
    )


def seed_all_teams(season: str = "2526", use_cache: bool = True) -> list[TeamWikiData]:
    """Scrape all La Liga teams and save to DB + cache."""
    import httpx

    cache_path = CACHE_PATH

    if use_cache:
        cached = load_cache(cache_path)
        if cached:
            print(f"Loaded {len(cached)} teams from cache")
            return cached

    teams = LALIGA_2526_TEAMS + SEGUNDA_2526_TEAMS

    client = httpx.Client(timeout=30)
    try:
        data = scrape_all_teams(client, teams, season)
    finally:
        client.close()

    # Save to DB
    conn = sqlite3.connect(DB_PATH)
    init_team_features(conn)
    for d in data:
        imputed = len(d.missing_fields) > 3
        upsert_team_features(conn, d, imputed=imputed)
    conn.commit()
    conn.close()

    # Save cache
    save_cache(data, cache_path)
    print(f"Scraped and saved {len(data)} teams")

    return data


def get_team_features(conn: sqlite3.Connection, team_id: str, season: str) -> Optional[dict]:
    """Get features for a specific team/season."""
    row = conn.execute(
        "SELECT * FROM team_features WHERE team_id = ? AND season = ?",
        (team_id, season),
    ).fetchone()
    if row:
        return dict(row)
    return None


def get_all_features(conn: sqlite3.Connection, season: str) -> dict[str, dict]:
    """Get all team features for a season as dict {team_id: row}."""
    rows = conn.execute(
        "SELECT * FROM team_features WHERE season = ?",
        (season,),
    ).fetchall()
    return {r["team_id"]: dict(r) for r in rows}
