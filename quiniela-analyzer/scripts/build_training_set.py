"""Construye training_set_v3.parquet uniendo odds + form + h2h + rest.

Output: data/training_set_v3.parquet con 1 fila por partido y features anti-leakage.
"""
from __future__ import annotations

import argparse
import logging
import sqlite3
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "quiniela.db"
OUT = ROOT / "data" / "training_set_v3.parquet"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)


def build() -> pd.DataFrame:
    conn = sqlite3.connect(DB)
    log.info("Construyendo training set unificado...")

    df = pd.read_sql_query("""
        SELECT
            m.match_id, m.season, m.division, m.jornada, m.matchday_date,
            m.home_team, m.away_team, m.home_goals, m.away_goals, m.result
        FROM matches m
        WHERE m.result IS NOT NULL
    """, conn)

    # Odds (Task 1)
    odds = pd.read_sql_query("""
        SELECT match_id, imp_h, imp_d, imp_a, avg_h, avg_d, avg_a,
               psc_h, psc_d, psc_a
        FROM match_odds
    """, conn)
    df = df.merge(odds, on="match_id", how="left")

    # Form (Task 2) — usa schema legacy (f5_*, f10_*)
    form = pd.read_sql_query("""
        SELECT match_id,
               f5_wins_home AS home_n5_w, f5_draws_home AS home_n5_d,
               f5_losses_home AS home_n5_l,
               f5_wins_away AS away_n5_w, f5_draws_away AS away_n5_d,
               f5_losses_away AS away_n5_l,
               f10_wins_home AS home_n10_wins, f10_points_home AS home_n10_points_avg,
               f10_wins_away AS away_n10_wins, f10_points_away AS away_n10_points_avg,
               f5_win_streak_home AS home_win_streak,
               f5_unbeaten_streak_away AS away_unbeaten_streak,
               f5_points_diff AS form_diff_n5,
               f10_points_diff AS form_diff_n10
        FROM match_form
    """, conn)
    df = df.merge(form, on="match_id", how="left")

    # H2H (Task 3) — usa schema legacy (h2h5_*, h2h10_*)
    h2h = pd.read_sql_query("""
        SELECT match_id,
               h2h5_wins_home AS h2h5_home_wins,
               h2h5_draws_home AS h2h5_draws,
               h2h5_losses_home AS h2h5_away_wins,
               h2h10_wins_home AS h2h10_home_wins,
               h2h10_draws_home AS h2h10_draws,
               h2h10_losses_home AS h2h10_away_wins
        FROM match_h2h
    """, conn)
    df = df.merge(h2h, on="match_id", how="left")

    # Rest (Task 4)
    rest = pd.read_sql_query("""
        SELECT match_id, rest_days_home, rest_days_away, rest_days_diff
        FROM match_rest
    """, conn)
    df = df.merge(rest, on="match_id", how="left")

    # Drop partidos sin odds (crítico: odds es nuestra señal principal)
    n_before = len(df)
    df = df.dropna(subset=["avg_h"])
    log.info(f"Tras filtrar partidos con odds: {len(df)}/{n_before}")

    conn.close()
    return df


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", default=str(OUT))
    args = p.parse_args()

    df = build()
    log.info(f"Training set: {df.shape[0]} partidos × {df.shape[1]} columnas")

    feature_cols = [c for c in df.columns
                    if c not in ("match_id", "season", "division", "jornada",
                                 "matchday_date", "home_team", "away_team",
                                 "home_goals", "away_goals", "result")]
    print("\nCobertura por feature:")
    for c in feature_cols:
        cov = 100 * df[c].notna().sum() / len(df)
        print(f"  {c:25s} {cov:.1f}%")

    print("\nDistribución de resultados:")
    print(df["result"].value_counts(normalize=True).round(3))

    print("\nReparto por temporada:")
    print(df["season"].value_counts().sort_index())

    out = Path(args.out)
    out.parent.mkdir(exist_ok=True)
    df.to_parquet(out)
    log.info(f"Guardado en {out}")


if __name__ == "__main__":
    main()