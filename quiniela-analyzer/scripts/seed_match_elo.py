"""Materializa match_elo: ELO_home/away/diff ANTES del partido (no después).

Los ratings en elo_ratings están con match_date = matchday (POST-partido).
Para un partido con matchday D, queremos el último rating con match_date < D
(o sea, POST del partido anterior, nunca POST del partido N).

Truco: shift de ratings +1 día → POST del día X = 'rating antes del día X+1'.
"""
import logging
import sqlite3
from datetime import timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "quiniela.db"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)


def main():
    conn = sqlite3.connect(DB)
    log.info("Cargando matches...")
    matches = pd.read_sql_query("""
        SELECT match_id, matchday_date, home_team, away_team
        FROM matches
        WHERE result IS NOT NULL AND matchday_date IS NOT NULL
        ORDER BY matchday_date
    """, conn)
    log.info(f"Partidos: {len(matches)}")

    log.info("Cargando elo_ratings...")
    ratings = pd.read_sql_query("SELECT team_id, match_date, elo FROM elo_ratings", conn)
    ratings["match_date"] = pd.to_datetime(ratings["match_date"])
    log.info(f"Ratings: {len(ratings)}")

    matches["matchday_date"] = pd.to_datetime(matches["matchday_date"])

    # Shift: rating POST del día X se convierte en 'PRE del día X+1'.
    ratings["match_date_eff"] = ratings["match_date"] + timedelta(days=1)
    ratings_eff = ratings[["team_id", "match_date_eff", "elo"]].rename(
        columns={"match_date_eff": "match_date"}).sort_values("match_date")

    # ELO home: último rating con match_date_eff <= matchday_date (estricto contra POST del mismo día)
    home_df = matches[["match_id", "home_team", "matchday_date"]].rename(
        columns={"home_team": "team_id", "matchday_date": "match_date"}).sort_values("match_date")
    elo_home = pd.merge_asof(home_df, ratings_eff, on="match_date", by="team_id",
                              direction="backward")[["match_id", "elo"]].rename(columns={"elo": "elo_home"})

    away_df = matches[["match_id", "away_team", "matchday_date"]].rename(
        columns={"away_team": "team_id", "matchday_date": "match_date"}).sort_values("match_date")
    elo_away = pd.merge_asof(away_df, ratings_eff, on="match_date", by="team_id",
                              direction="backward")[["match_id", "elo"]].rename(columns={"elo": "elo_away"})

    df = matches.merge(elo_home, on="match_id", how="left").merge(elo_away, on="match_id", how="left")
    df["elo_diff"] = df["elo_home"] - df["elo_away"]
    df["elo_home_adv"] = df["elo_home"] + 80.0

    conn.execute("""
        CREATE TABLE IF NOT EXISTS match_elo (
            match_id INTEGER PRIMARY KEY,
            elo_home REAL,
            elo_away REAL,
            elo_diff REAL,
            elo_home_adv REAL,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("DELETE FROM match_elo")
    conn.commit()

    out = df[["match_id", "elo_home", "elo_away", "elo_diff", "elo_home_adv"]]
    out.to_sql("match_elo", conn, if_exists="append", index=False)

    cur = conn.cursor()
    n_filled = cur.execute("SELECT COUNT(*) FROM match_elo WHERE elo_home IS NOT NULL").fetchone()[0]
    n_total = cur.execute("SELECT COUNT(*) FROM match_elo").fetchone()[0]
    log.info(f"✅ match_elo: {n_total} filas, {n_filled} con ELO_home non-null ({100*n_filled/n_total:.1f}%)")

    stats = cur.execute("SELECT AVG(elo_home), AVG(elo_away), AVG(elo_diff) FROM match_elo").fetchone()
    log.info(f"  avg home: {stats[0]:.1f}, away: {stats[1]:.1f}, diff: {stats[2]:+.1f}")
    conn.close()


if __name__ == "__main__":
    main()
