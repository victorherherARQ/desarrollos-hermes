"""Feature join: build training set parquet from all available features.

Features per match:
- ELO_home, ELO_away, ELO_diff
- stadium_capacity_home, stadium_capacity_away
- name_embedding_home[25], name_embedding_away[25]
- news_score_home, news_score_away (0.0 if NULL)
- result (H/D/A) as target

Output: data/features/training_set.parquet
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from datetime import date, timedelta

import pandas as pd

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "quiniela.db"
OUT_PATH = Path(__file__).resolve().parents[2] / "data" / "features" / "training_set.parquet"


def get_elo(conn: sqlite3.Connection, team_id: str, as_of: str) -> float | None:
    """Get ELO rating as of a date."""
    row = conn.execute(
        """SELECT elo FROM elo_ratings
           WHERE team_id = ? AND match_date <= ?
           ORDER BY match_date DESC LIMIT 1""",
        (team_id, as_of),
    ).fetchone()
    return row[0] if row else None


def get_stadium_capacity(conn: sqlite3.Connection, team_id: str, season: str) -> float | None:
    row = conn.execute(
        """SELECT stadium_capacity FROM team_features
           WHERE team_id = ? AND season = ?""",
        (team_id, season),
    ).fetchone()
    return row[0] if row else None


def get_name_embedding(conn: sqlite3.Connection, team_id: str) -> list[float]:
    row = conn.execute(
        "SELECT name_embedding FROM teams WHERE team_id = ?",
        (team_id,),
    ).fetchone()
    if row and row[0]:
        return json.loads(row[0])
    return [0.0] * 25


def get_news_score(conn: sqlite3.Connection, team_id: str, as_of: str) -> float:
    row = conn.execute(
        """SELECT score_mean FROM news_scores
           WHERE team_id = ? AND as_of <= ?
           ORDER BY as_of DESC LIMIT 1""",
        (team_id, as_of),
    ).fetchone()
    return row[0] if row else 0.0


def build_feature_row(conn: sqlite3.Connection, row: tuple) -> dict | None:
    """Build a feature dict for a single match row."""
    (
        match_id, season, division, jornada,
        matchday_date, home_team, away_team,
        home_goals, away_goals, result,
    ) = row

    if home_goals is None or away_goals is None:
        return None

    # ELO ratings
    elo_home = get_elo(conn, home_team, matchday_date)
    elo_away = get_elo(conn, away_team, matchday_date)

    # Stadium capacity
    cap_home = get_stadium_capacity(conn, home_team, season)
    cap_away = get_stadium_capacity(conn, away_team, season)

    # Name embeddings
    emb_home = get_name_embedding(conn, home_team)
    emb_away = get_name_embedding(conn, away_team)

    # News scores
    news_home = get_news_score(conn, home_team, matchday_date)
    news_away = get_news_score(conn, away_team, matchday_date)

    # Build row dict
    feat: dict = {
        "match_id": match_id,
        "season": season,
        "division": division,
        "jornada": jornada,
        "matchday_date": matchday_date,
        "home_team": home_team,
        "away_team": away_team,
        "ELO_home": elo_home or 1500.0,
        "ELO_away": elo_away or 1500.0,
        "ELO_diff": (elo_home or 1500.0) - (elo_away or 1500.0),
        "stadium_capacity_home": cap_home or 0.0,
        "stadium_capacity_away": cap_away or 0.0,
        "news_score_home": news_home,
        "news_score_away": news_away,
        "result": result,
    }

    # Embedding columns
    for i, v in enumerate(emb_home):
        feat[f"emb_home_{i}"] = v
    for i, v in enumerate(emb_away):
        feat[f"emb_away_{i}"] = v

    return feat


def build_training_set(conn: sqlite3.Connection, output_path: Path = OUT_PATH) -> pd.DataFrame:
    """Build the full training set parquet from all matches."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    rows = conn.execute("""
        SELECT match_id, season, division, jornada, matchday_date,
               home_team, away_team, home_goals, away_goals, result
        FROM matches
        WHERE home_goals IS NOT NULL
          AND away_goals IS NOT NULL
          AND result IS NOT NULL
        ORDER BY matchday_date ASC
    """).fetchall()

    features = []
    for row in rows:
        feat = build_feature_row(conn, row)
        if feat:
            features.append(feat)

    df = pd.DataFrame(features)

    # Ensure correct column order
    base_cols = [
        "match_id", "season", "division", "jornada", "matchday_date",
        "home_team", "away_team",
        "ELO_home", "ELO_away", "ELO_diff",
        "stadium_capacity_home", "stadium_capacity_away",
        "news_score_home", "news_score_away",
    ]
    emb_cols = [c for c in df.columns if c.startswith("emb_")]
    target_col = ["result"]
    ordered = [c for c in base_cols if c in df.columns] + sorted(emb_cols) + [c for c in target_col if c in df.columns]
    df = df[ordered]

    df.to_parquet(output_path, index=False)
    print(f"✅ Saved training set: {len(df)} rows, {len(df.columns)} cols → {output_path}")

    return df


def load_training_set(path: Path = OUT_PATH) -> pd.DataFrame:
    return pd.read_parquet(path)


if __name__ == "__main__":
    conn = sqlite3.connect(DB_PATH)
    df = build_training_set(conn)
    print(f"\nFeature columns: {df.columns.tolist()}")
    print(f"\nShape: {df.shape}")
    print(f"\nSample row:\n{df.iloc[0]}")
    conn.close()
