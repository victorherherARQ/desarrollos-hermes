"""Valida si 'rest_days' (descanso entre partidos) es predictivo.

Hipótesis: equipos con poco descanso (3-4 días) pierden más que los que vienen
de descansar 7+ días.
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
               r.rest_days_home, r.rest_days_away, r.rest_days_diff,
               r.played_within_4d_home AS home_within_4d,
               r.played_within_4d_away AS away_within_4d
        FROM matches m
        JOIN match_rest r ON r.match_id = m.match_id
        WHERE m.result IS NOT NULL
          AND r.rest_days_home IS NOT NULL
          AND r.rest_days_away IS NOT NULL
        """,
        conn,
    )
    print(f"Total partidos con rest: {len(df)}")
    base_h = (df["result"] == "H").mean()
    base_d = (df["result"] == "D").mean()
    base_a = (df["result"] == "A").mean()
    print(f"Baseline: H={base_h:.3f}, D={base_d:.3f}, A={base_a:.3f}")
    print()

    # Distribución de rest_days_home
    print("=== Distribución rest_days_home ===")
    for thr in [0, 2, 3, 4, 5, 6, 7]:
        n = (df["rest_days_home"] <= thr).sum()
        n_strict = ((df["rest_days_home"] == thr) & (df["rest_days_home"].notna())).sum()
        print(f"  rest_days_home <= {thr}: {n} ({100*n/len(df):.1f}%) | ={thr}: {n_strict}")
    print()

    # ¿Equipos con poco descanso (3-4d) ganan menos?
    print("=== Accuracy por rest_days_home ===")
    bins = [0, 2, 3, 4, 5, 6, 7, 14, 30, 365]
    labels = ["[0-2]d", "[3]d", "[4]d", "[5]d", "[6]d", "[7]d", "[8-14]d", "[15-30]d", "[31+]d"]
    df["bin"] = pd.cut(df["rest_days_home"], bins=bins, labels=labels, right=True)
    for b, g in df.groupby("bin", observed=True):
        acc_h = (g["result"] == "H").mean()
        acc_d = (g["result"] == "D").mean()
        acc_a = (g["result"] == "A").mean()
        print(f"  {b:10s}: n={len(g):5d}  H={acc_h:.3f}  D={acc_d:.3f}  A={acc_a:.3f}")
    print()

    # ¿LOCAL con poco descanso local pierde?
    print("=== Local con poco descanso (≤4d) vs local descansado (≥7d) ===")
    short = df[df["home_within_4d"] == 1]
    rested = df[df["home_within_4d"] == 0]
    if len(short) > 0 and len(rested) > 0:
        print(f"  short   (n={len(short)}): H={(short['result']=='H').mean():.3f}  D={(short['result']=='D').mean():.3f}  A={(short['result']=='A').mean():.3f}")
        print(f"  rested  (n={len(rested)}): H={(rested['result']=='H').mean():.3f}  D={(rested['result']=='D').mean():.3f}  A={(rested['result']=='A').mean():.3f}")
    print()

    # Visitante con poco descanso pierde visita
    print("=== Visitante con poco descanso (≤4d) vs descansado (≥7d) ===")
    if len(df[df["away_within_4d"] == 1]) > 0 and len(df[df["away_within_4d"] == 0]) > 0:
        short_a = df[df["away_within_4d"] == 1]
        rested_a = df[df["away_within_4d"] == 0]
        print(f"  short   (n={len(short_a)}): H={(short_a['result']=='H').mean():.3f}  D={(short_a['result']=='D').mean():.3f}  A={(short_a['result']=='A').mean():.3f}")
        print(f"  rested  (n={len(rested_a)}): H={(rested_a['result']=='H').mean():.3f}  D={(rested_a['result']=='D').mean():.3f}  A={(rested_a['result']=='A').mean():.3f}")
    print()

    # Correlación
    import numpy as np
    corr = np.corrcoef(
        df["rest_days_home"].values,
        (df["result"] == "H").astype(int).values,
    )[0, 1]
    print(f"=== Correlación ===")
    print(f"  corr(rest_days_home, result==H) = {corr:+.4f}")
    corr_diff = np.corrcoef(
        df["rest_days_diff"].values,
        (df["result"] == "H").astype(int).values,
    )[0, 1]
    print(f"  corr(rest_days_diff, result==H) = {corr_diff:+.4f}")

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
