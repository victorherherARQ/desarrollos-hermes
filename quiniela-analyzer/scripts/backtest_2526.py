"""Backtest: ejecuta propuesta para TODAS las jornadas 2025-26 y mide accuracy.

Compara:
  - Baseline: 1 siempre (siempre apostar local)
  - AvgH: argmax(avg_h, avg_d, avg_a)
  - Modelo v3 (TODO, cuando esté entrenado)

Input: BD con matches + match_odds + quiniela_calendar
Output: tabla quiniela_proposals + accuracy global
"""
from __future__ import annotations

import argparse
import logging
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "quiniela.db"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)


def predict_1x2(avg_h, avg_d, avg_a) -> str:
    """Predice 1/X/2 a partir de avg_h, avg_d, avg_a.

    Returns: 'H', 'D', 'A' (mismo formato que matches.result).
    """
    if avg_h is None or avg_d is None or avg_a is None:
        return "H"
    h, d, a = 1.0/avg_h, 1.0/avg_d, 1.0/avg_a
    s = h + d + a
    h, d, a = h/s, d/s, a/s
    if h >= d and h >= a:
        return "H"
    elif d >= a:
        return "D"
    return "A"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--season", default="2526")
    args = p.parse_args()

    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    # Para cada jornada con partidos, juntar partidos y comparar pred
    total = 0
    correct_local = 0
    correct_avgh = 0

    for j in range(1, 39):
        r = cur.execute(
            "SELECT fecha_sabado, fecha_lunes FROM quiniela_calendar WHERE jornada=? AND season=?",
            (j, args.season),
        ).fetchone()
        if not r:
            continue
        fecha_sabado, fecha_lunes = r
        matches = cur.execute(
            """
            SELECT m.match_id, m.result, o.avg_h, o.avg_d, o.avg_a
            FROM matches m
            LEFT JOIN match_odds o ON m.match_id = o.match_id
            WHERE m.matchday_date BETWEEN ? AND ?
                  AND m.result IS NOT NULL
            """,
            (fecha_sabado, fecha_lunes),
        ).fetchall()
        for m_id, result, ah, ad, aa in matches:
            total += 1
            # baseline local
            if result == "H":
                correct_local += 1
            # AvgH
            pred = predict_1x2(ah, ad, aa)
            if pred == result:
                correct_avgh += 1

    print(f"\n=== BACKTEST QUINIELA {args.season} ===")
    print(f"Total partidos: {total}")
    print(f"Baseline (siempre 1): {correct_local}/{total} = {100*correct_local/total:.2f}%")
    print(f"AvgH argmax: {correct_avgh}/{total} = {100*correct_avgh/total:.2f}%")
    print(f"Incremento: {correct_avgh - correct_local} partidos ({100*(correct_avgh/total - correct_local/total):+.2f}pp)")
    conn.close()


if __name__ == "__main__":
    main()