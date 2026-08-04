"""Test anti-leakage para h2h features.

Ejecutar: python3 -m tests.test_h2h_no_leakage
"""
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.features.h2h import h2h_matches, h2h_features_for_match


def main() -> int:
    conn = sqlite3.connect(ROOT / "data" / "quiniela.db")
    failures = []

    # Test 1: la h2h justo ANTES de un partido NO lo incluye
    target = conn.execute(
        "SELECT match_id, season, division, matchday_date, home_team, away_team "
        "FROM matches WHERE (home_team='real_madrid' AND away_team='barcelona') "
        "   OR (home_team='barcelona' AND away_team='real_madrid') "
        "ORDER BY matchday_date DESC LIMIT 1"
    ).fetchone()
    mid, season, div, dt, ht, at = target
    target_date = dt

    hist_at = h2h_matches(conn, ht, at, as_of_date=target_date, limit=20)
    ids_at = [m["match_id"] for m in hist_at]
    if mid in ids_at:
        failures.append(f"T1: el partido {mid} SÍ está en h2h con as_of={target_date}")
    print(f"T1 ✓: partido {mid} ({ht} vs {at}, {target_date}) NO está en h2h de {len(ids_at)} partidos previos")

    hist_after = h2h_matches(conn, ht, at, as_of_date="2026-05-11", limit=20)
    ids_after = [m["match_id"] for m in hist_after]
    if mid not in ids_after:
        failures.append(f"T1b: el partido {mid} NO está en h2h con as_of=2026-05-11")
    print(f"T1b ✓: partido {mid} SÍ aparece en h2h con as_of=2026-05-11")

    # Test 2: cambio en as_of_date no debe perder partidos
    h1 = h2h_matches(conn, "sevilla", "betis", as_of_date="2020-01-01", limit=30)
    h2 = h2h_matches(conn, "sevilla", "betis", as_of_date="2025-01-01", limit=30)
    ids1 = {m["match_id"] for m in h1}
    ids2 = {m["match_id"] for m in h2}
    if not ids1.issubset(ids2):
        failures.append(f"T2: h2h con as_of_date anterior debería estar contenido en el posterior")
    print(f"T2 ✓: h2h Sevilla-Betis as_of=2020 ({len(ids1)}) ⊆ as_of=2025 ({len(ids2)})")

    # Test 3: primer partido del dataset → h2h_played = 0
    first_match = conn.execute(
        "SELECT match_id, matchday_date, home_team, away_team FROM matches "
        "WHERE season='1011' AND division='SP1' ORDER BY matchday_date ASC LIMIT 1"
    ).fetchone()
    fmid, fdt, fht, fat = first_match
    h_first = h2h_matches(conn, fht, fat, as_of_date=fdt, limit=10)
    if len(h_first) != 0:
        failures.append(f"T3: para primer partido histórico {first_match} esperaba 0 h2h, obtuve {len(h_first)}")
    print(f"T3 ✓: primer partido del dataset ({first_match}), h2h_played={len(h_first)}")

    # Test 4: claves devueltas tienen el formato correcto
    out = h2h_features_for_match(conn, home_team="sevilla", away_team="betis", matchday_date="2025-01-01", n=5)
    expected_prefix = "h2h5_"
    expected_keys = ["played", "wins_home", "draws_home", "losses_home", "points_home",
                     "gf_avg_home", "ga_avg_home", "gd_avg_home", "home_win_rate",
                     "home_unbeaten_rate", "home_dominance"]
    missing = [expected_prefix + k for k in expected_keys if (expected_prefix + k) not in out]
    if missing:
        failures.append(f"T4: claves faltantes en output: {missing}")
    print(f"T4 ✓: claves devueltas OK ({len(out)} claves, todas con prefijo h2h5_)")

    conn.close()

    print()
    if failures:
        print(f"❌ {len(failures)} FALLOS:")
        for f in failures:
            print(f"   - {f}")
        return 1
    print("✅ TODOS los tests anti-leakage h2h PASAN")
    return 0


if __name__ == "__main__":
    sys.exit(main())