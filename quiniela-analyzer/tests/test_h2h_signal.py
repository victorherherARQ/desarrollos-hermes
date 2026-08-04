"""Valida que la señal 'h2h' (head-to-head) es predictiva.

Hipótesis: si el equipo local tiene buen balance h2h reciente, tiene ventaja
adicional sobre la forma reciente.

Análisis:
  1. Distribución: cuántas parejas tienen histórico?
  2. Accuracy por cuantil de h2h_home_win_rate
  3. ¿Derbis donde h2h está roto cambian accuracy?
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    conn = sqlite3.connect(ROOT / "data" / "quiniela.db")
    pd = __import__("pandas")
    df = pd.read_sql_query(
        """
        SELECT m.match_id, m.season, m.division, m.result,
               h.h2h5_played AS h2h5_played,
               h.h2h5_home_win_rate AS h2h5_winr,
               h.h2h5_home_unbeaten_rate AS h2h5_unbeatenr,
               h.h2h5_home_dominance AS h2h5_dom,
               h.h2h10_played AS h2h10_played,
               h.h2h10_home_win_rate AS h2h10_winr,
               h.h2h10_home_dominance AS h2h10_dom
        FROM matches m
        JOIN match_h2h h ON h.match_id = m.match_id
        WHERE m.result IS NOT NULL
        """,
        conn,
    )
    print(f"Total partidos: {len(df)}")
    base_h = (df["result"] == "H").mean()
    print(f"Baseline always_H: {base_h:.4f}")
    print()

    # Distribución por disponibilidad de h2h
    print("=== Disponibilidad de h2h ===")
    for thr in [0, 1, 3, 5, 10]:
        n = (df["h2h5_played"] >= thr).sum()
        print(f"  h2h5_played >= {thr}: {n} ({100*n/len(df):.1f}%)")
    print()

    # Cuartiles de h2h5_win_rate (sólo donde hay al menos 3 h2h)
    sub = df[df["h2h5_played"] >= 3].copy()
    print(f"=== Accuracy por cuartil de h2h5_win_rate (n={len(sub)}) ===")
    sub["q"] = pd.qcut(sub["h2h5_winr"], 4, labels=["Q1", "Q2", "Q3", "Q4 (home domina)"])
    for q, g in sub.groupby("q", observed=True):
        acc_h = (g["result"] == "H").mean()
        print(f"  {q}: n={len(g)}  H={acc_h:.3f} (baseline {base_h:.3f})")
    print()

    # Correlación entre h2h_home_win_rate y result==H
    print("=== Correlación ===")
    is_home = (df["result"] == "H").astype(int).values
    import numpy as np
    for col in ["h2h5_winr", "h2h5_unbeatenr", "h2h5_dom", "h2h10_winr", "h2h10_dom"]:
        sub = df[df[f"{col.split('_')[0]}_played"] >= 3]
        corr = np.corrcoef(sub[col].values, (sub["result"] == "H").astype(int).values)[0, 1]
        print(f"  corr({col}, result==H) = {corr:+.4f} (n={len(sub)})")
    print()

    # Parejas con más h2h (rivalidades clásicas)
    print("=== Top 10 parejas con más h2h en el dataset ===")
    parejas = pd.read_sql_query(
        """
        WITH pairs AS (
          SELECT LEAST(home_team, away_team) AS a,
                 GREATEST(home_team, away_team) AS b,
                 match_id
          FROM matches
          WHERE season IN ('2425','2526')
        )
        SELECT a, b, COUNT(*) AS n
        FROM pairs
        GROUP BY a, b
        ORDER BY n DESC
        LIMIT 10
        """,
        conn,
    )
    for _, r in parejas.iterrows():
        print(f"  {r['a']:20s} vs {r['b']:20s}: {r['n']:3d} partidos")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())