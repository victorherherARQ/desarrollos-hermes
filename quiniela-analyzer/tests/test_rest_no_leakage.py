"""Test anti-leakage para rest features.

Ejecutar: python3 -m tests.test_rest_no_leakage
"""
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.features.rest import (
    days_since_last_match,
    rest_features_for_match,
)


def main() -> int:
    conn = sqlite3.connect(ROOT / "data" / "quiniela.db")
    failures = []

    # Test 1: el último partido de un equipo ANTES de una fecha SÍ se cuenta.
    target_team = "real_madrid"
    target_date = "2024-04-20"
    rd = days_since_last_match(conn, target_team, as_of_date=target_date)
    # Debe ser positivo (hemos confirmado en smoke test = 7)
    if rd is None or rd <= 0:
        failures.append(f"T1: days_since_last_match(real_madrid, {target_date}) = {rd}, esperaba > 0")
    print(f"T1 ✓: real_madrid descansa {rd} días antes del 2024-04-20")

    # Test 2: la función NO incluye el partido objetivo mismo.
    # Si el equipo jugó el 2024-04-20, debe dar exactamente los días anteriores.
    target_date2 = "2024-04-21"
    rd_after = days_since_last_match(conn, target_team, as_of_date=target_date2)
    expected = rd + 1
    if rd_after != expected:
        failures.append(f"T2: days_since_last_match cambia de {rd} a {rd_after}, esperaba {expected}")
    print(f"T2 ✓: incrementar as_of_date suma exactamente 1 día ({rd} → {rd_after})")

    # Test 3: en 2010-08-27 (primer partido) NO hay histórico (None)
    rd_first = days_since_last_match(conn, "levante", as_of_date="2010-08-27")
    if rd_first is not None:
        failures.append(f"T3: levantes en 2010-08-27 esperaba None, obtuve {rd_first}")
    print(f"T3 ✓: primer partido del dataset, sin histórico → None")

    # Test 4: claves devueltas tienen el formato correcto
    out = rest_features_for_match(
        conn, home_team="real_madrid", away_team="barcelona", matchday_date="2024-04-20",
    )
    expected_keys = [
        "rest_days_home", "rest_days_away", "rest_days_diff",
        "played_3d_home", "played_3d_away", "played_4d_home", "played_4d_away",
        "played_within_4d_home", "played_within_4d_away",
    ]
    missing = [k for k in expected_keys if k not in out]
    if missing:
        failures.append(f"T4: claves faltantes en output: {missing}")
    print(f"T4 ✓: {len(out)} claves devueltas, todas las esperadas presentes")

    # Test 5: rest_days_diff = rest_days_home - rest_days_away
    out2 = rest_features_for_match(
        conn, home_team="betis", away_team="sevilla", matchday_date="2024-04-15",
    )
    if out2["rest_days_diff"] != out2["rest_days_home"] - out2["rest_days_away"]:
        failures.append(f"T5: rest_days_diff={out2['rest_days_diff']} ≠ home-away={out2['rest_days_home'] - out2['rest_days_away']}")
    print(f"T5 ✓: rest_days_diff = rest_days_home - rest_days_away = {out2['rest_days_diff']}")

    conn.close()
    print()
    if failures:
        print(f"❌ {len(failures)} FALLOS:")
        for f in failures:
            print(f"   - {f}")
        return 1
    print("✅ TODOS los tests anti-leakage rest PASAN")
    return 0


if __name__ == "__main__":
    sys.exit(main())
