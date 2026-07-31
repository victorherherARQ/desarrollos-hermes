"""Repositorio SQLite para partidos de fútbol y quinielas.

Tablas:
    matches        — un partido de fútbol con goles, equipos, fecha, temporada
    teams          — catálogo de equipos LaLiga 1ª/2ª
    quiniela_jornadas  — metadatos de cada jornada de La Quiniela
    quiniela_partidos  — los 15 partidos de cada jornada con resultado
    quinigol_jornadas  — metadatos del Quinigol
    quinigol_partidos  — los 6 partidos del Quinigol con marcador
    elo_ratings    — snapshot de ELO por equipo en cada fecha (cache)
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Iterator

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "quiniela.db"


SCHEMA = """
CREATE TABLE IF NOT EXISTS teams (
    team_id      TEXT PRIMARY KEY,        -- 'laliga_real_madrid', 'laliga_barcelona', etc.
    name         TEXT NOT NULL UNIQUE,    -- nombre canónico en español
    division     TEXT NOT NULL,           -- 'SP1' o 'SP2'
    country      TEXT NOT NULL DEFAULT 'Spain'
);

CREATE TABLE IF NOT EXISTS matches (
    match_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    season        TEXT NOT NULL,          -- '2526' (2025-26)
    division      TEXT NOT NULL,          -- 'SP1' o 'SP2'
    jornada       INTEGER NOT NULL,       -- jornada de liga (1-38)
    matchday_date DATE NOT NULL,          -- fecha del partido
    home_team     TEXT NOT NULL,          -- FK a teams.team_id
    away_team     TEXT NOT NULL,
    home_goals    INTEGER,
    away_goals    INTEGER,
    result        TEXT,                   -- 'H' home win / 'D' draw / 'A' away win
    source        TEXT DEFAULT 'football-data.co.uk',
    UNIQUE(season, division, matchday_date, home_team, away_team)
);
CREATE INDEX IF NOT EXISTS idx_matches_date ON matches(matchday_date);
CREATE INDEX IF NOT EXISTS idx_matches_season ON matches(season);
CREATE INDEX IF NOT EXISTS idx_matches_home ON matches(home_team);
CREATE INDEX IF NOT EXISTS idx_matches_away ON matches(away_team);

CREATE TABLE IF NOT EXISTS elo_ratings (
    team_id    TEXT NOT NULL,
    match_date DATE NOT NULL,
    elo        REAL NOT NULL,
    PRIMARY KEY (team_id, match_date)
);

CREATE TABLE IF NOT EXISTS quiniela_jornadas (
    jornada_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    season      TEXT NOT NULL,            -- '2526'
    numero      INTEGER NOT NULL,         -- número de jornada (1, 2, ...)
    fecha       DATE,                     -- fecha de cierre
    UNIQUE(season, numero)
);

CREATE TABLE IF NOT EXISTS quiniela_partidos (
    partido_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    jornada_id   INTEGER NOT NULL REFERENCES quiniela_jornadas(jornada_id),
    orden        INTEGER NOT NULL,        -- 1..15
    home_team    TEXT NOT NULL,
    away_team    TEXT NOT NULL,
    home_goals   INTEGER,
    away_goals   INTEGER,
    sign         TEXT,                    -- '1' / 'X' / '2'
    pleno        TEXT,                    -- signo del Pleno al 15: '0' / '1' / '2' / 'M'
    UNIQUE(jornada_id, orden)
);

CREATE TABLE IF NOT EXISTS quinigol_jornadas (
    jornada_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    season      TEXT NOT NULL,
    numero      INTEGER NOT NULL,
    fecha       DATE,
    UNIQUE(season, numero)
);

CREATE TABLE IF NOT EXISTS quinigol_partidos (
    partido_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    jornada_id   INTEGER NOT NULL REFERENCES quinigol_jornadas(jornada_id),
    orden        INTEGER NOT NULL,        -- 1..6
    home_team    TEXT NOT NULL,
    away_team    TEXT NOT NULL,
    home_goals   INTEGER,
    away_goals   INTEGER,
    UNIQUE(jornada_id, orden)
);
"""


def _slugify(name: str) -> str:
    """Stable, lowercase, ASCII-ish slug for a team name.

    Examples
    --------
    >>> _slugify("Real Madrid")
    'real_madrid'
    >>> _slugify("RC Celta de Vigo")
    'rc_celta_vigo'
    """
    s = name.lower()
    # Drop accents
    replacements = {
        "á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u",
        "à": "a", "è": "e", "ì": "i", "ò": "o", "ù": "u",
        "ñ": "n", "ç": "c",
    }
    for a, b in replacements.items():
        s = s.replace(a, b)
    s = s.replace("'", "")
    s = s.replace("-", " ")
    out = []
    for token in s.split():
        token = token.strip(".,()")
        if token:
            out.append(token)
    return "_".join(out) or "unknown"


def team_id(name: str) -> str:
    return _slugify(name)


@contextmanager
def get_connection(db_path: Path | str | None = None) -> Iterator[sqlite3.Connection]:
    """Yield a sqlite3 connection with row_factory=Row. Auto-commits
    on clean exit, rolls back on exception.
    """
    path = Path(db_path) if db_path else DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_schema(db_path: Path | str | None = None) -> None:
    with get_connection(db_path) as conn:
        conn.executescript(SCHEMA)


def upsert_team(conn: sqlite3.Connection, name: str, division: str) -> str:
    """Insert a team if missing. Returns its team_id."""
    tid = team_id(name)
    conn.execute(
        """
        INSERT INTO teams(team_id, name, division)
        VALUES(?, ?, ?)
        ON CONFLICT(team_id) DO UPDATE
        SET name = excluded.name
        """,
        (tid, name, division),
    )
    return tid


def upsert_match(
    conn: sqlite3.Connection,
    *,
    season: str,
    division: str,
    jornada: int,
    matchday_date: date,
    home_team: str,
    away_team: str,
    home_goals: int | None,
    away_goals: int | None,
    source: str = "football-data.co.uk",
) -> int:
    """Insert or update a match. Returns the match_id."""
    home_id = upsert_team(conn, home_team, division)
    away_id = upsert_team(conn, away_team, division)

    if home_goals is not None and away_goals is not None:
        if home_goals > away_goals:
            result = "H"
        elif home_goals < away_goals:
            result = "A"
        else:
            result = "D"
    else:
        result = None

    cur = conn.execute(
        """
        INSERT INTO matches(
            season, division, jornada, matchday_date,
            home_team, away_team, home_goals, away_goals, result, source
        )
        VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(season, division, matchday_date, home_team, away_team)
        DO UPDATE SET
            home_goals = excluded.home_goals,
            away_goals = excluded.away_goals,
            result = excluded.result,
            jornada = excluded.jornada
        """,
        (season, division, jornada, matchday_date.isoformat(),
         home_id, away_id, home_goals, away_goals, result, source),
    )
    return cur.lastrowid