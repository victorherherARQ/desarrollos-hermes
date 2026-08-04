"""Valida que la señal 'forma reciente' es predictiva.

Hipótesis: si el equipo local tiene MEJOR forma reciente que el visitante, el
resultado H es más probable que la media.

Tres análisis:
  1. Accuracy predicción naïve: si form_score_diff > threshold → H, si < -threshold → A, else D
  2. Comparación con baseline always_H
  3. Tabla por cuartiles de diferencia de forma
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    conn = sqlite3.connect(ROOT / "data" / "quiniela.db")
    df = __import__("pandas").read_sql_query(
        """
        SELECT m.match_id, m.season, m.division, m.result,
               mf.f5_points_diff AS p5_diff,
               mf.f10_points_diff AS p10_diff,
               mf.f5_score_diff  AS s5_diff,
               mf.f10_score_diff AS s10_diff,
               mf.f5_win_streak_home AS ws5_h,
               mf.f5_win_streak_away AS ws5_a
        FROM matches m
        JOIN match_form mf ON mf.match_id = m.match_id
        WHERE m.result IS NOT NULL
          AND mf.f5_n_played_home = 5
          AND mf.f5_n_played_away = 5
        """,
        conn,
    )
    print(f"Total partidos con ventana completa N=5: {len(df)}")

    base_h = (df["result"] == "H").mean()
    print(f"Baseline always_H: {base_h:.4f}")
    print()

    # ── Test 1: predicción naïve basada en form_score_diff (N=10) ──
    print("=== Test 1: predicción naïve con form_score_diff (N=10) ===")
    thresholds = [0.0, 0.1, 0.15, 0.2, 0.25, 0.3]
    for thr in thresholds:
        pred = []
        for _, r in df.iterrows():
            if r["s10_diff"] > thr:
                pred.append("H")
            elif r["s10_diff"] < -thr:
                pred.append("A")
            else:
                pred.append("D")
        pred = np.array(pred)
        acc = (pred == df["result"].values).mean()
        n_h = (pred == "H").sum()
        n_d = (pred == "D").sum()
        n_a = (pred == "A").sum()
        delta = acc - base_h
        print(f"  thr={thr:.2f} acc={acc:.4f} delta={delta*100:+.2f}pp H={n_h} D={n_d} A={n_a}")

    print()

    # ── Test 2: por cuartiles de form_score_diff (N=5) ──
    print("=== Test 2: accuracy por cuartil de f5_points_diff ===")
    df["p5_q"] = pd_q = __import__("pandas").qcut(df["p5_diff"], 4, labels=["Q1 (home<away)", "Q2", "Q3", "Q4 (home>away)"])
    for q, sub in df.groupby("p5_q", observed=True):
        n = len(sub)
        acc_h = (sub["result"] == "H").mean()
        acc_d = (sub["result"] == "D").mean()
        acc_a = (sub["result"] == "A").mean()
        print(f"  {q}: n={n}  H={acc_h:.3f}  D={acc_d:.3f}  A={acc_a:.3f}")

    print()

    # ── Test 3: home con win_streak ≥3 ──
    print("=== Test 3: racha de victorias (home) ===")
    sub = df[df["ws5_h"] >= 3]
    if len(sub) > 0:
        acc_h = (sub["result"] == "H").mean()
        print(f"  Home con racha ≥3 (n={len(sub)}): local gana {acc_h:.3f} vs baseline {base_h:.3f}")
    sub = df[df["ws5_a"] >= 3]
    if len(sub) > 0:
        acc_a = (sub["result"] == "A").mean()
        print(f"  Away con racha ≥3 (n={len(sub)}): visitante gana {acc_a:.3f}")

    print()

    # ── Test 4: correlación entre form_diff y "H" binario ──
    print("=== Test 4: correlación ===")
    is_home = (df["result"] == "H").astype(int).values
    for col in ["p5_diff", "p10_diff", "s5_diff", "s10_diff"]:
        corr = np.corrcoef(df[col].values, is_home)[0, 1]
        print(f"  corr({col}, result==H) = {corr:+.4f}")

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())