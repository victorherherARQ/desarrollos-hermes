"""Head-to-head features: historial entre dos equipos antes de un partido.

Para cada partido, calculamos el balance de los N partidos anteriores entre
exactamente esos dos equipos (misma pareja, da igual el orden de local/visitante).

Features generadas (N=5, N=10):

    h2h{N}_played          partidos del h2h encontrados
    h2h{N}_wins_home       victorias del equipo local (en este partido)
    h2h{N}_draws_home      empates
    h2h{N}_losses_home     derrotas
    h2h{N}_points_home     puntos (3W + 1D + 0L) del local
    h2h{N}_gf_avg_home     goles a favor promedio del local
    h2h{N}_ga_avg_home     goles en contra promedio del local
    h2h{N}_gd_avg_home     gol-average del local
    h2h{N}_home_win_rate   wins_home / played
    h2h{N}_home_unbeaten_rate  (wins_home + draws_home) / played
    h2h{N}_home_dominance  wins_home - losses_home

Importante: el c\u00e1lculo es "rolling window" sobre partidos ANTERIORES a la fecha
del partido objetivo. Sin leakage temporal.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "quiniela.db"


def h2h_matches(
    conn: sqlite3.Connection,
    home_team: str,
    away_team: str,
    *,
    as_of_date: str,
    limit: int = 30,
) -> list[dict]:
    """Devuelve los \u00faltimos `limit` partidos entre home_team y away_team
    anteriores a as_of_date, en cualquier local/visitante.
    """
    rows = conn.execute(
        """
        SELECT match_id, season, division, matchday_date,
               home_team, away_team, home_goals, away_goals, result
        FROM matches
        WHERE result IS NOT NULL
          AND matchday_date < ?
          AND ((home_team = ? AND away_team = ?)
            OR (home_team = ? AND away_team = ?))
        ORDER BY matchday_date DESC
        LIMIT ?
        """,
        (as_of_date, home_team, away_team, away_team, home_team, limit),
    ).fetchall()

    history = []
    for r in rows:
        mid, season, division, dt, ht, at, hg, ag, res = r
        if ht == home_team:
            gf, ga = hg, ag
            h_team_in_match = home_team
        else:
            gf, ga = ag, hg
            h_team_in_match = away_team
        if res == "H":
            points = 3 if h_team_in_match == home_team else 0
        elif res == "A":
            points = 0 if h_team_in_match == home_team else 3
        else:
            points = 1
        history.append({
            "match_id": mid,
            "season": season,
            "division": division,
            "matchday_date": dt,
            "home_team_in_match": h_team_in_match,
            "home_team": ht,
            "away_team": at,
            "gf": gf,
            "ga": ga,
            "result": res,
            "points": points,
        })
    return history


def h2h_for_match(
    conn: sqlite3.Connection,
    home_team: str,
    away_team: str,
    *,
    as_of_date: str,
    n: int = 5,
) -> dict:
    """Calcula features h2h sobre los \u00faltimos N partidos entre estos dos equipos."""
    history = h2h_matches(conn, home_team, away_team, as_of_date=as_of_date, limit=n)

    if not history:
        return {
            "played": 0,
            "wins_home": 0,
            "draws_home": 0,
            "losses_home": 0,
            "points_home": 0,
            "gf_avg_home": 0.0,
            "ga_avg_home": 0.0,
            "gd_avg_home": 0.0,
            "home_win_rate": 0.0,
            "home_unbeaten_rate": 0.0,
            "home_dominance": 0,
        }

    wins = sum(1 for m in history if m["points"] == 3)
    draws = sum(1 for m in history if m["points"] == 1)
    losses = sum(1 for m in history if m["points"] == 0)
    points = sum(m["points"] for m in history)
    gf = sum(m["gf"] for m in history)
    ga = sum(m["ga"] for m in history)

    n_played = len(history)
    return {
        "played": n_played,
        "wins_home": wins,
        "draws_home": draws,
        "losses_home": losses,
        "points_home": points,
        "gf_avg_home": gf / n_played,
        "ga_avg_home": ga / n_played,
        "gd_avg_home": (gf - ga) / n_played,
        "home_win_rate": wins / n_played,
        "home_unbeaten_rate": (wins + draws) / n_played,
        "home_dominance": wins - losses,
    }


def h2h_features_for_match(
    conn: sqlite3.Connection,
    *,
    home_team: str,
    away_team: str,
    matchday_date: str,
    n: int = 5,
) -> dict:
    """Wrapper que renombra claves h2h_* a h2h{N}_* (sin doble prefijo)."""
    raw = h2h_for_match(conn, home_team, away_team, as_of_date=matchday_date, n=n)
    out = {}
    for k, v in raw.items():
        key = k[4:] if k.startswith("h2h_") else k
        out[f"h2h{n}_{key}"] = v
    return out


# \u2500\u2500 Smoke test \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

if __name__ == "__main__":
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    print("=== Test 1: 'El Cl\u00e1sico' (Barcelona vs Real Madrid) ===")
    row = conn.execute(
        "SELECT match_id, season, division, matchday_date, home_team, away_team "
        "FROM matches WHERE (home_team='real_madrid' AND away_team='barcelona') "
        "   OR (home_team='barcelona' AND away_team='real_madrid') "
        "ORDER BY matchday_date DESC LIMIT 1"
    ).fetchone()
    mid, season, div, dt, ht, at = row
    print(f"Partido: {mid} | {ht} vs {at} | {dt}")
    h2h5 = h2h_features_for_match(conn, home_team=ht, away_team=at, matchday_date=dt, n=5)
    h2h10 = h2h_features_for_match(conn, home_team=ht, away_team=at, matchday_date=dt, n=10)
    print("N=5:")
    for k, v in h2h5.items():
        print(f"  {k:30s} = {v}")
    print("N=10:")
    for k, v in h2h10.items():
        print(f"  {k:30s} = {v}")

    print()
    print("=== Test 2: Derbi Sevilla vs Betis ===")
    row = conn.execute(
        "SELECT match_id, season, division, matchday_date, home_team, away_team "
        "FROM matches WHERE (home_team='sevilla' AND away_team='betis') "
        "   OR (home_team='betis' AND away_team='sevilla') "
        "ORDER BY matchday_date DESC LIMIT 1"
    ).fetchone()
    mid, season, div, dt, ht, at = row
    print(f"Partido: {mid} | {ht} vs {at} | {dt}")
    h2h = h2h_features_for_match(conn, home_team=ht, away_team=at, matchday_date=dt, n=10)
    for k, v in h2h.items():
        print(f"  {k:30s} = {v}")

    print()
    print("=== Test 3: Verificar formato de claves (sin doble prefijo) ===")
    out = h2h_features_for_match(conn, home_team="sevilla", away_team="betis", matchday_date="2025-01-01", n=5)
    has_double = [k for k in out.keys() if k.startswith("h2h5_h2h_")]
    print(f"  claves con doble prefijo: {has_double}")
    print(f"  total claves: {len(out)}")
    print(f"  ejemplo: {list(out.keys())[:3]}")

    conn.close()
