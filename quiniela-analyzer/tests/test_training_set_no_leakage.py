"""Test anti-leakage del training_set_v3.

Verifica:
  1. Las features de forma (f5_*, f10_*) son asof: para un partido dado,
     NO incluyen ese partido ni futuros.
  2. Las features h2h son asof: para un partido dado, NO incluyen ese partido.
  3. Las features rest son asof: rest_days se calcula desde la fecha del partido.

Ejecutar: python3 -m tests.test_training_set_no_leakage
"""
import sqlite3
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DB = ROOT / "data" / "quiniela.db"


def test_form_asof() -> bool:
    """f5_wins_home en match_id=4 NO debe incluir el propio match_id=4."""
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    # match_id=4 = alaves vs levante, 2025-08-16
    # f5_wins_home = nº partidos ganados de alaves en sus 5 partidos anteriores
    # Verificación manual: ¿alaves jugó antes del 2025-08-16?
    rows = cur.execute("""
        SELECT m.match_id, m.matchday_date, m.result, m.home_team, m.away_team
        FROM matches m
        WHERE (m.home_team = 'alaves' OR m.away_team = 'alaves')
          AND m.matchday_date < '2025-08-16'
          AND m.result IS NOT NULL
        ORDER BY m.matchday_date DESC
        LIMIT 5
    """).fetchall()
    print(f"\nÚltimos 5 partidos de alaves ANTES del 2025-08-16:")
    for r in rows:
        print(f"  {r[1]} {r[3]} vs {r[4]} ({r[2]})")

    # f5_wins_home declarado
    val = cur.execute("""
        SELECT f5_wins_home, f5_n_played_home FROM match_form WHERE match_id = 4
    """).fetchone()
    print(f"\nf5_wins_home declarado: {val[0]} (n_played={val[1]})")

    # Cuenta manual
    n_wins = 0
    for r in rows:
        m_id, date, result, home, away = r
        if home == "alaves":
            if result == "H":
                n_wins += 1
        else:
            if result == "A":
                n_wins += 1

    print(f"Cuenta manual de wins: {n_wins} (de {len(rows)} partidos)")
    ok = val[0] == n_wins and val[1] == len(rows)
    print(f"✅ Form asof OK" if ok else f"❌ LEAKAGE en form!")
    conn.close()
    return ok


def test_h2h_asof() -> bool:
    """h2h5_home_wins para match_id=4 NO incluye el propio match_id."""
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    # match_id=4 = alaves vs levante, 2025-08-16
    rows = cur.execute("""
        SELECT m.match_id, m.matchday_date, m.result
        FROM matches m
        WHERE ((m.home_team = 'alaves' AND m.away_team = 'levante')
               OR (m.home_team = 'levante' AND m.away_team = 'alaves'))
          AND m.matchday_date < '2025-08-16'
          AND m.result IS NOT NULL
        ORDER BY m.matchday_date DESC
        LIMIT 5
    """).fetchall()
    print(f"\nÚltimos 5 H2H alaves-levante ANTES del 2025-08-16:")
    for r in rows:
        print(f"  match_id={r[0]} {r[1]} ({r[2]})")

    val = cur.execute("""
        SELECT h2h5_wins_home, h2h5_played FROM match_h2h WHERE match_id = 4
    """).fetchone()
    print(f"\nh2h5_wins_home declarado: {val[0]} (played={val[1]})")
    print(f"✅ H2H played <= {len(rows)} → {'OK' if val[1] <= len(rows) else 'LEAKAGE'}")
    conn.close()
    return val[1] <= len(rows)


def test_rest_asof() -> bool:
    """rest_days_home para match_id=4 = días desde último partido de alaves."""
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    # match_id=4 = alaves vs levante, 2025-08-16 (sábado)
    last_match = cur.execute("""
        SELECT m.match_id, m.matchday_date
        FROM matches m
        WHERE (m.home_team = 'alaves' OR m.away_team = 'alaves')
          AND m.matchday_date < '2025-08-16'
          AND m.result IS NOT NULL
        ORDER BY m.matchday_date DESC
        LIMIT 1
    """).fetchone()

    from datetime import date
    last_date = date.fromisoformat(last_match[1])
    match_date = date(2025, 8, 16)
    expected = (match_date - last_date).days

    val = cur.execute("""
        SELECT rest_days_home FROM match_rest WHERE match_id = 4
    """).fetchone()

    print(f"\nrest_days_home declarado: {val[0]}, esperado: {expected}")
    ok = val[0] == expected
    print(f"✅ Rest asof OK" if ok else f"❌ LEAKAGE en rest!")
    conn.close()
    return ok


def main():
    print("=" * 60)
    print("TEST ANTI-LEAKAGE training_set_v3")
    print("=" * 60)
    results = []
    results.append(("Form asof", test_form_asof()))
    results.append(("H2H asof", test_h2h_asof()))
    results.append(("Rest asof", test_rest_asof()))

    print("\n" + "=" * 60)
    print("RESUMEN:")
    for name, ok in results:
        print(f"  {'✅' if ok else '❌'} {name}")
    print(f"Total: {sum(r[1] for r in results)}/{len(results)} pasaron")


if __name__ == "__main__":
    main()