"""Team form features: rachas y momentum antes de cada partido.

Para cada partido, calculamos cómo iba el equipo en los N partidos ANTERIORES
(sin incluir el partido actual — eso sería leakage temporal).

Features generadas (N=5 y N=10):
    points_lastN       puntos en últimos N (3W + 1D + 0L)
    wins_lastN         victorias en últimos N
    draws_lastN        empates en últimos N
    losses_lastN       derrotas en últimos N
    gf_avg_lastN       goles a favor promedio en últimos N
    ga_avg_lastN       goles en contra promedio en últimos N
    gd_avg_lastN       gol average promedio en últimos N
    win_streak         racha actual de victorias consecutivas (0 si última fue D o L)
    unbeaten_streak    racha actual sin perder (incluye D)
    form_score_lastN   puntos / (3*N) — [0,1], resumen normalizado

Importante: el cálculo es "rolling window" sobre partidos anteriores a la fecha
del partido objetivo. Sin leakage.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "quiniela.db"


def team_matches_history(
    conn: sqlite3.Connection,
    team_id: str,
    *,
    as_of_date: str,
    limit: int = 30,
) -> list[dict]:
    """Devuelve los últimos `limit` partidos del equipo anteriores a as_of_date.

    Returns
    -------
    list of dict con: match_id, season, division, matchday_date,
                      opponent, home_away, gf, ga, result, points.
    """
    rows = conn.execute(
        """
        SELECT match_id, season, division, matchday_date,
               home_team, away_team, home_goals, away_goals, result
        FROM matches
        WHERE result IS NOT NULL
          AND matchday_date < ?
          AND (home_team = ? OR away_team = ?)
        ORDER BY matchday_date DESC
        LIMIT ?
        """,
        (as_of_date, team_id, team_id, limit),
    ).fetchall()

    history = []
    for r in rows:
        mid, season, division, dt, ht, at, hg, ag, res = r
        if ht == team_id:
            gf, ga = hg, ag
            opp = at
            home_away = "H"
        else:
            gf, ga = ag, hg
            opp = ht
            home_away = "A"
        if res == "H":
            points = 3 if home_away == "H" else 0
        elif res == "A":
            points = 0 if home_away == "H" else 3
        else:
            points = 1
        history.append({
            "match_id": mid,
            "season": season,
            "division": division,
            "matchday_date": dt,
            "opponent": opp,
            "home_away": home_away,
            "gf": gf,
            "ga": ga,
            "result": res if home_away == "H" else ("A" if res == "H" else ("H" if res == "A" else "D")),
            "points": points,
        })
    return history


def form_for_team(
    conn: sqlite3.Connection,
    team_id: str,
    *,
    as_of_date: str,
    n: int = 5,
) -> dict:
    """Calcula features de forma sobre los últimos N partidos anteriores a as_of_date.

    Returns
    -------
    dict con:
        n_played          partidos disponibles (puede ser < n al inicio de temporada)
        points_lastN
        wins_lastN
        draws_lastN
        losses_lastN
        gf_avg_lastN
        ga_avg_lastN
        gd_avg_lastN
        win_streak
        unbeaten_streak
        form_score_lastN   points_lastN / (3*n)
    """
    history = team_matches_history(conn, team_id, as_of_date=as_of_date, limit=n)
    # history ya viene DESC; invertimos a ASC para que las rachas se midan desde el
    # más antiguo al más reciente
    history.reverse()

    if not history:
        return {
            "n_played": 0,
            "points_lastN": 0,
            "wins_lastN": 0,
            "draws_lastN": 0,
            "losses_lastN": 0,
            "gf_avg_lastN": 0.0,
            "ga_avg_lastN": 0.0,
            "gd_avg_lastN": 0.0,
            "win_streak": 0,
            "unbeaten_streak": 0,
            "form_score_lastN": 0.0,
        }

    wins = sum(1 for m in history if m["points"] == 3)
    draws = sum(1 for m in history if m["points"] == 1)
    losses = sum(1 for m in history if m["points"] == 0)
    points = sum(m["points"] for m in history)
    gf = sum(m["gf"] for m in history)
    ga = sum(m["ga"] for m in history)

    # Rachas: contamos desde el partido más reciente hacia atrás
    win_streak = 0
    unbeaten_streak = 0
    for m in reversed(history):
        if m["points"] == 3:
            win_streak += 1
            unbeaten_streak += 1
        elif m["points"] == 1:
            win_streak = 0  # corta racha de victorias pero no de invicto
            unbeaten_streak += 1
        else:  # derrota
            break

    return {
        "n_played": len(history),
        "points_lastN": points,
        "wins_lastN": wins,
        "draws_lastN": draws,
        "losses_lastN": losses,
        "gf_avg_lastN": gf / len(history),
        "ga_avg_lastN": ga / len(history),
        "gd_avg_lastN": (gf - ga) / len(history),
        "win_streak": win_streak,
        "unbeaten_streak": unbeaten_streak,
        "form_score_lastN": points / (3.0 * n) if n > 0 else 0.0,
    }


def form_features_for_match(
    conn: sqlite3.Connection,
    *,
    season: str,
    division: str,
    home_team: str,
    away_team: str,
    matchday_date: str,
    n: int = 5,
) -> dict:
    """Forma para ambos equipos antes de un partido. Devuelve un dict con claves:

        form{N}_points_home, form{N}_points_away, form{N}_points_diff,
        form{N}_wins_home, form{N}_wins_away, form{N}_gf_avg_home,
        form{N}_ga_avg_home, form{N}_gd_avg_home, form{N}_gd_avg_away,
        form{N}_win_streak_home, form{N}_win_streak_away,
        form{N}_unbeaten_streak_home, form{N}_unbeaten_streak_away,
        form{N}_score_home, form{N}_score_away, form{N}_score_diff
    """
    home_form = form_for_team(conn, home_team, as_of_date=matchday_date, n=n)
    away_form = form_for_team(conn, away_team, as_of_date=matchday_date, n=n)

    out = {}
    for prefix, src in (("home", home_form), ("away", away_form)):
        out[f"form{n}_points_{prefix}"] = src["points_lastN"]
        out[f"form{n}_wins_{prefix}"] = src["wins_lastN"]
        out[f"form{n}_draws_{prefix}"] = src["draws_lastN"]
        out[f"form{n}_losses_{prefix}"] = src["losses_lastN"]
        out[f"form{n}_gf_avg_{prefix}"] = src["gf_avg_lastN"]
        out[f"form{n}_ga_avg_{prefix}"] = src["ga_avg_lastN"]
        out[f"form{n}_gd_avg_{prefix}"] = src["gd_avg_lastN"]
        out[f"form{n}_win_streak_{prefix}"] = src["win_streak"]
        out[f"form{n}_unbeaten_streak_{prefix}"] = src["unbeaten_streak"]
        out[f"form{n}_score_{prefix}"] = src["form_score_lastN"]
        # Disponibilidad (para saber si la ventana estaba completa)
        out[f"form{n}_n_played_{prefix}"] = src["n_played"]

    # Diferencias home-away (más útiles para el modelo)
    out[f"form{n}_points_diff"] = home_form["points_lastN"] - away_form["points_lastN"]
    out[f"form{n}_gd_diff"] = home_form["gd_avg_lastN"] - away_form["gd_avg_lastN"]
    out[f"form{n}_score_diff"] = home_form["form_score_lastN"] - away_form["form_score_lastN"]
    out[f"form{n}_win_streak_diff"] = home_form["win_streak"] - away_form["win_streak"]

    return out


# ── Smoke test ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    print("=== Test 1: Real Madrid 2024-04-15 (después de racha Champions) ===")
    feats = form_features_for_match(
        conn, season="2425", division="SP1",
        home_team="real_madrid", away_team="cadiz",
        matchday_date="2024-04-15", n=5,
    )
    for k, v in feats.items():
        print(f"  {k:30s} = {v}")

    print()
    print("=== Test 2: Partido inicio de temporada (pocos partidos jugados) ===")
    feats = form_features_for_match(
        conn, season="2526", division="SP1",
        home_team="sevilla", away_team="valencia",
        matchday_date="2025-08-17", n=5,
    )
    for k, v in feats.items():
        print(f"  {k:30s} = {v}")

    print()
    print("=== Test 3: forma con N=10 ===")
    feats = form_features_for_match(
        conn, season="2425", division="SP1",
        home_team="barcelona", away_team="sevilla",
        matchday_date="2024-10-20", n=10,
    )
    for k, v in feats.items():
        print(f"  {k:30s} = {v}")

    conn.close()
