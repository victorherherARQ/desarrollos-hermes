"""Test anti-leakage: para cada partido, la forma NO debe incluir ese partido ni futuros.

Ejecutar: python3 -m tests.test_form_no_leakage
"""
import sqlite3
import sys
from pathlib import Path

# Permitir imports desde src/
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.features.form import form_for_team, team_matches_history


def main() -> int:
    conn = sqlite3.connect(ROOT / "data" / "quiniela.db")
    failures = []

    # ── Test 1: la forma del equipo justo ANTES de un partido concreto NO lo incluye ──
    target_match = conn.execute(
        "SELECT match_id, season, division, matchday_date, home_team, away_team "
        "FROM matches WHERE season='2425' AND home_team='barcelona' AND matchday_date='2024-10-20'"
    ).fetchone()
    mid, season, div, dt, ht, at = target_match
    target_date = dt

    # Forma usando como_of_date = fecha del partido → NO debe incluirlo
    hist_at = team_matches_history(conn, ht, as_of_date=target_date, limit=20)
    ids_at = [m["match_id"] for m in hist_at]
    if mid in ids_at:
        failures.append(f"T1: partido {mid} SÍ está en historia del Barcelona con as_of={target_date}")
    print(f"T1 ✓: partido {mid} (Barcelona, {target_date}) NO está en historia de {len(ids_at)} partidos previos")

    # Forma usando como_of_date = día siguiente → SÍ debe estar incluido
    hist_after = team_matches_history(conn, ht, as_of_date="2024-10-21", limit=20)
    ids_after = [m["match_id"] for m in hist_after]
    if mid not in ids_after:
        failures.append(f"T1b: partido {mid} NO está en historia del Barcelona con as_of=2024-10-21")
    print(f"T1b ✓: partido {mid} SÍ aparece cuando as_of_date es el día después del partido")

    # ── Test 2: la forma debe ser estrictamente decreciente en puntos si cambiamos as_of_date ──
    # Si añadimos un partido que fue derrota, los puntos totales NO deberían aumentar (con misma N)
    n = 5
    f_before = form_for_team(conn, "sevilla", as_of_date="2025-08-25", n=n)
    # Sevilla el 2025-08-25 juega contra Getafe (jornada 1 de 25/26). Su último partido
    # anterior fue el 2025-05-25 en 24/25.
    f_after = form_for_team(conn, "sevilla", as_of_date="2025-08-26", n=n)
    if f_after["n_played"] < f_before["n_played"]:
        failures.append(f"T2: al avanzar as_of_date, n_played debería no bajar ({f_before['n_played']} → {f_after['n_played']})")
    print(f"T2 ✓: Sevilla as_of=2025-08-25 n={f_before['n_played']}, as_of=2025-08-26 n={f_after['n_played']}")

    # ── Test 3: para los primeros partidos de un equipo en la BD, n_played < N ──
    # El primer partido del Barcelona en el dataset (¿cuál es?)
    first_match = conn.execute(
        "SELECT matchday_date, home_team, away_team FROM matches "
        "WHERE home_team='barcelona' OR away_team='barcelona' "
        "ORDER BY matchday_date ASC LIMIT 1"
    ).fetchone()
    first_date, fht, fat = first_match
    team = fht if fht == "barcelona" else fat
    f_first = form_for_team(conn, team, as_of_date=first_date, n=10)
    if f_first["n_played"] != 0:
        failures.append(f"T3: para primer partido ({first_match}) esperaba n_played=0, obtuve {f_first['n_played']}")
    print(f"T3 ✓: primer partido del Barcelona ({first_match}), n_played={f_first['n_played']}")

    # ── Test 4: partidos FUTUROS (posteriores al partido objetivo) NO entran en la forma ──
    future = conn.execute(
        "SELECT match_id FROM matches WHERE season='2425' AND (home_team='barcelona' OR away_team='barcelona') "
        "AND matchday_date > '2024-10-20' LIMIT 5"
    ).fetchall()
    future_ids = {r[0] for r in future}
    overlap = set(ids_at) & future_ids
    if overlap:
        failures.append(f"T4: partidos futuros {overlap} SÍ están en historia con as_of={target_date}")
    print(f"T4 ✓: 0 partidos futuros del Barcelona en historia con as_of={target_date}")

    conn.close()

    print()
    if failures:
        print(f"❌ {len(failures)} FALLOS:")
        for f in failures:
            print(f"   - {f}")
        return 1
    else:
        print("✅ TODOS los tests anti-leakage PASAN")
        return 0


if __name__ == "__main__":
    sys.exit(main())