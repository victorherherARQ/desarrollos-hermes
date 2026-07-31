"""News sentiment scoring using Spanish football lexicon.

Aggregates news_signals into per-team, per-day sentiment scores.
Stores results in `news_scores` table.

DB schema:
    CREATE TABLE news_scores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        team_id TEXT NOT NULL,
        as_of TEXT NOT NULL,        -- date (YYYY-MM-DD)
        score_mean REAL NOT NULL,   -- mean sentiment [-1, +1]
        score_count INTEGER NOT NULL,
        pos_count INTEGER,
        neg_count INTEGER,
        UNIQUE(team_id, as_of)
    );
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import Optional

from .lexicon_es import get_sentiment_score

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "quiniela.db"


def init_news_scores(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS news_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_id TEXT NOT NULL,
            as_of TEXT NOT NULL,
            score_mean REAL NOT NULL,
            score_count INTEGER NOT NULL,
            pos_count INTEGER,
            neg_count INTEGER,
            UNIQUE(team_id, as_of)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_news_scores_team ON news_scores(team_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_news_scores_date ON news_scores(as_of)")


def compute_daily_scores(conn: sqlite3.Connection, as_of: date) -> list[dict]:
    """Compute aggregated sentiment scores for all teams on a given date.

    Returns list of dicts with team_id, score_mean, score_count, pos_count, neg_count.
    """
    # Get signals for this date or the last N days
    cutoff = (as_of - timedelta(days=7)).isoformat()
    rows = conn.execute(
        """SELECT team_id, headline FROM news_signals
           WHERE pub_date >= ? AND pub_date <= ?
           ORDER BY team_id, pub_date DESC""",
        (cutoff, as_of.isoformat() + "T23:59:59"),
    ).fetchall()

    from collections import defaultdict
    team_headlines: dict[str, list[str]] = defaultdict(list)
    for team_id, headline in rows:
        team_headlines[team_id].append(headline)

    results = []
    for team_id, headlines in team_headlines.items():
        pos_total = neg_total = 0
        scores = []
        for h in headlines:
            pos, neg, score = get_sentiment_score(h)
            pos_total += pos
            neg_total += neg
            scores.append(score)

        score_count = len(scores)
        score_mean = sum(scores) / score_count if score_count else 0.0
        results.append({
            "team_id": team_id,
            "as_of": as_of.isoformat(),
            "score_mean": round(score_mean, 4),
            "score_count": score_count,
            "pos_count": pos_total,
            "neg_count": neg_total,
        })
    return results


def update_news_scores(conn: sqlite3.Connection, as_of: date) -> int:
    """Compute and upsert daily scores. Returns number of teams scored."""
    scores = compute_daily_scores(conn, as_of)
    for s in scores:
        conn.execute(
            """INSERT INTO news_scores (team_id, as_of, score_mean, score_count, pos_count, neg_count)
               VALUES (:team_id, :as_of, :score_mean, :score_count, :pos_count, :neg_count)
               ON CONFLICT(team_id, as_of) DO UPDATE SET
                   score_mean = excluded.score_mean,
                   score_count = excluded.score_count,
                   pos_count = excluded.pos_count,
                   neg_count = excluded.neg_count""",
            s,
        )
    return len(scores)


def seed_all_news_scores(days_back: int = 30) -> int:
    """Seed news_scores for the last N days."""
    conn = sqlite3.connect(DB_PATH)
    init_news_scores(conn)

    today = date.today()
    total_teams = 0
    for d in range(days_back + 1):
        as_of = today - timedelta(days=d)
        n = update_news_scores(conn, as_of)
        if n > 0:
            print(f"  {as_of}: {n} teams scored")
            total_teams += n

    conn.commit()
    conn.close()
    return total_teams


def get_team_score(conn: sqlite3.Connection, team_id: str, as_of: date) -> Optional[float]:
    """Get the most recent news score for a team up to a given date."""
    row = conn.execute(
        """SELECT score_mean FROM news_scores
           WHERE team_id = ? AND as_of <= ?
           ORDER BY as_of DESC LIMIT 1""",
        (team_id, as_of.isoformat()),
    ).fetchone()
    return row[0] if row else None


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Compute news sentiment scores")
    parser.add_argument("--days", type=int, default=30, help="Days back to compute")
    args = parser.parse_args()

    print(f"Computing news scores for last {args.days} days...")
    n = seed_all_news_scores(days_back=args.days)
    print(f"\n✅ Done — {n} team-day scores computed")
