"""Rest/fatigue features: días desde el último partido del equipo.

Proxy barato de fatiga por calendario (Champions/Europa). Equipos que jugaron
hace 3-4 días suelen venir de UEFA entre semana; los que descansan 7+ días
vienen "frescos".

Features:
    rest_days_home         días desde el último partido del local
    rest_days_away         días desde el último partido del visitante
    rest_days_diff         home - away (positivo = local más fresco)
    played_3d_home         1 si el local jugó hace 3 días (Champions/Europa)
    played_3d_away         1 si el visitante jugó hace 3 días
    played_4d_home         1 si el local jugó hace 4 días
    played_4d_away         1 si el visitante jugó hace 4 días

Importante: el cálculo es "días desde el último partido con matchday_date
< partido objetivo". Sin leakage temporal.
"""
from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "quiniela.db"


def days_since_last_match(
    conn: sqlite3.Connection,
    team: str,
    *,
    as_of_date: str,
) -> int | None:
    """Días desde el último partido del equipo anterior a as_of_date.

    Returns
    -------
    int o None si el equipo nunca jugó antes.
    """
    row = conn.execute(
        """
        SELECT MAX(matchday_date) FROM matches
        WHERE result IS NOT NULL
          AND matchday_date < ?
          AND (home_team = ? OR away_team = ?)
        """,
        (as_of_date, team, team),
    ).fetchone()
    if row is None or row[0] is None:
        return None
    last = date.fromisoformat(row[0])
    today = date.fromisoformat(as_of_date)
    return (today - last).days


def rest_features_for_match(
    conn: sqlite3.Connection,
    *,
    home_team: str,
    away_team: str,
    matchday_date: str,
) -> dict:
    """Calcula features de fatiga para un partido.

    Returns
    -------
    dict con claves:
        rest_days_home, rest_days_away, rest_days_diff,
        played_3d_home, played_3d_away, played_4d_home, played_4d_away,
        played_within_4d_home, played_within_4d_away
    """
    rd_home = days_since_last_match(conn, home_team, as_of_date=matchday_date)
    rd_away = days_since_last_match(conn, away_team, as_of_date=matchday_date)

    out = {
        "rest_days_home": rd_home,
        "rest_days_away": rd_away,
        "rest_days_diff": (rd_home - rd_away) if rd_home is not None and rd_away is not None else None,
        "played_3d_home": int(rd_home == 3) if rd_home is not None else 0,
        "played_3d_away": int(rd_away == 3) if rd_away is not None else 0,
        "played_4d_home": int(rd_home == 4) if rd_home is not None else 0,
        "played_4d_away": int(rd_away == 4) if rd_away is not None else 0,
        "played_within_4d_home": int(rd_home is not None and rd_home <= 4) if rd_home is not None else 0,
        "played_within_4d_away": int(rd_away is not None and rd_away <= 4) if rd_away is not None else 0,
    }
    return out


# ── Smoke test ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    print("=== Test 1: Real Madrid vs Cádiz 2024-04-15 ===")
    feats = rest_features_for_match(
        conn, home_team="real_madrid", away_team="cadiz", matchday_date="2024-04-15",
    )
    for k, v in feats.items():
        print(f"  {k:25s} = {v}")

    print()
    print("=== Test 2: Partido Champions mid-week (martes previo) ===")
    # El Madrid suele tener partido Champions el martes/miércoles. Buscamos un
    # partido de Liga que sea sábado con un martes Champions justo antes.
    feats = rest_features_for_match(
        conn, home_team="real_madrid", away_team="valencia", matchday_date="2024-04-20",
    )
    for k, v in feats.items():
        print(f"  {k:25s} = {v}")

    print()
    print("=== Test 3: Inicio de temporada (sin histórico) ===")
    feats = rest_features_for_match(
        conn, home_team="levante", away_team="vallecano", matchday_date="2010-08-27",
    )
    for k, v in feats.items():
        print(f"  {k:25s} = {v}")

    conn.close()
