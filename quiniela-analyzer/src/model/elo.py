"""ELO rating calculator for Spanish football teams.

Classic ELO with K=20. Processes all historical matches in chronological order
and stores ratings in `elo_ratings` table. Also computes a snapshot for 2526 season.

DB schema:
    CREATE TABLE elo_ratings (
        team_id    TEXT NOT NULL,
        match_date DATE NOT NULL,
        elo        REAL NOT NULL,
        PRIMARY KEY (team_id, match_date)
    );
"""
from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "quiniela.db"

INITIAL_ELO = 1500.0
K_FACTOR = 20.0
HOME_ADVANTAGE = 80.0  # ELO points


class EloCalculator:
    def __init__(self, k: float = K_FACTOR, home_adv: float = HOME_ADVANTAGE):
        self.k = k
        self.home_adv = home_adv
        self.ratings: dict[str, float] = {}
        self.history: list[tuple[str, str, str, float, float]] = (
            []
        )  # (match_date, team_id, opp_id, result, elo_after)

    def get_rating(self, team_id: str) -> float:
        return self.ratings.get(team_id, INITIAL_ELO)

    def expected(self, rating_a: float, rating_b: float) -> float:
        return 1.0 / (1.0 + 10.0 ** ((rating_b - rating_a) / 400.0))

    def update(
        self, team_id: str, opponent_id: str, homegoals: int, awaygoals: int, match_date: str
    ) -> float:
        """Update ELO for both teams. Returns new rating for team_id."""
        if team_id not in self.ratings:
            self.ratings[team_id] = INITIAL_ELO
        if opponent_id not in self.ratings:
            self.ratings[opponent_id] = INITIAL_ELO

        # Actual result: 1=win, 0.5=draw, 0=loss
        if homegoals > awaygoals:
            actual_home = 1.0
            actual_away = 0.0
        elif homegoals < awaygoals:
            actual_home = 0.0
            actual_away = 1.0
        else:
            actual_home = 0.5
            actual_away = 0.5

        # Home team gets home_advantage added to rating for expected calc
        r_home = self.ratings["home_team"] + self.home_adv
        r_away = self.ratings["away_team"]

        exp_home = self.expected(r_home, r_away)
        exp_away = 1.0 - exp_home

        new_home = self.ratings["home_team"] + self.k * (actual_home - exp_home)
        new_away = self.ratings["away_team"] + self.k * (actual_away - exp_away)

        self.ratings["home_team"] = new_home
        self.ratings["away_team"] = new_away

        self.history.append((match_date, "home_team", "away_team", actual_home, new_home))
        self.history.append((match_date, "away_team", "home_team", actual_away, new_away))

        return new_home

    def process_match(
        self, home_team: str, away_team: str, homegoals: int, awaygoals: int, match_date: str
    ) -> tuple[float, float]:
        """Process a single match. Returns (new_home_elo, new_away_elo)."""
        # Rename temporarily for update
        self.ratings["home_team"] = self.get_rating(home_team)
        self.ratings["away_team"] = self.get_rating(away_team)

        r_home = self.ratings["home_team"] + self.home_adv
        r_away = self.ratings["away_team"]

        exp_home = self.expected(r_home, r_away)
        exp_away = 1.0 - exp_home

        if homegoals > awaygoals:
            actual_home, actual_away = 1.0, 0.0
        elif homegoals < awaygoals:
            actual_home, actual_away = 0.0, 1.0
        else:
            actual_home, actual_away = 0.5, 0.5

        new_home = self.ratings["home_team"] + self.k * (actual_home - exp_home)
        new_away = self.ratings["away_team"] + self.k * (actual_away - exp_away)

        self.ratings[home_team] = new_home
        self.ratings[away_team] = new_away

        # Log history
        self.history.append((match_date, home_team, away_team, homegoals, new_home))
        self.history.append((match_date, away_team, home_team, awaygoals, new_away))

        # Clean temp keys
        for k in ["home_team", "away_team"]:
            if k in self.ratings and k not in self.ratings:
                del self.ratings[k]

        return new_home, new_away


def init_elo_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS elo_ratings (
            team_id    TEXT NOT NULL,
            match_date DATE NOT NULL,
            elo        REAL NOT NULL,
            PRIMARY KEY (team_id, match_date)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_elo_team ON elo_ratings(team_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_elo_date ON elo_ratings(match_date)")

    # Clear old ratings
    conn.execute("DELETE FROM elo_ratings")


def compute_elo_ratings(conn: sqlite3.Connection, save: bool = True) -> dict[str, float]:
    """Process all matches chronologically and compute ELO ratings.

    Returns final ratings dict {team_id: elo}.
    """
    init_elo_table(conn)

    # Clear old ratings
    conn.execute("DELETE FROM elo_ratings")

    # Fetch all matches ordered by date
    rows = conn.execute("""
        SELECT match_id, season, matchday_date, home_team, away_team,
               home_goals, away_goals, result
        FROM matches
        WHERE home_goals IS NOT NULL AND away_goals IS NOT NULL
        ORDER BY matchday_date ASC, match_id ASC
    """).fetchall()

    calc = EloCalculator()

    for row in rows:
        match_id, season, match_date, home_team, away_team = row[0], row[1], row[2], row[3], row[4]
        home_goals, away_goals = row[5], row[6]

        if home_goals is None or away_goals is None:
            continue

        calc.process_match(home_team, away_team, home_goals, away_goals, match_date)

    # Store all ratings
    if save:
        for team_id, elo in calc.ratings.items():
            # Store with the last date in history
            last_date = conn.execute(
                """SELECT MAX(matchday_date) FROM matches
                   WHERE home_team = ? OR away_team = ?""",
                (team_id, team_id),
            ).fetchone()[0]
            if last_date:
                conn.execute(
                    "INSERT OR REPLACE INTO elo_ratings (team_id, match_date, elo) VALUES (?, ?, ?)",
                    (team_id, last_date, elo),
                )

    conn.commit()
    print(f"✅ ELO computed for {len(calc.ratings)} teams, {len(calc.history)} history entries")

    return calc.ratings


def get_elo_at_date(conn: sqlite3.Connection, team_id: str, as_of: str) -> Optional[float]:
    """Get the ELO rating for a team as of a specific date (inclusive)."""
    row = conn.execute(
        """SELECT elo FROM elo_ratings
           WHERE team_id = ? AND match_date <= ?
           ORDER BY match_date DESC LIMIT 1""",
        (team_id, as_of),
    ).fetchone()
    return row[0] if row else None


def get_current_elo(conn: sqlite3.Connection, team_id: str) -> Optional[float]:
    """Get the most recent ELO for a team."""
    row = conn.execute(
        """SELECT elo FROM elo_ratings
           WHERE team_id = ?
           ORDER BY match_date DESC LIMIT 1""",
        (team_id,),
    ).fetchone()
    return row[0] if row else None


def get_elo_snapshot(conn: sqlite3.Connection, season: str = "2526") -> dict[str, float]:
    """Get ELO ratings for all teams at the start of a season."""
    # The start date for season "2526" is approximately 2025-08-01
    # We approximate using a date range
    season_start_map = {
        "2526": "2025-08-01",
        "2425": "2024-08-01",
        "2324": "2023-08-01",
        "2223": "2022-08-01",
        "2122": "2021-08-01",
        "2021": "2021-08-01",
        "2022": "2022-08-01",
        "2023": "2023-08-01",
        "2024": "2024-08-01",
        "2025": "2025-08-01",
    }
    as_of = season_start_map.get(season, "2025-08-01")

    rows = conn.execute(
        """SELECT team_id, elo FROM elo_ratings
           WHERE match_date <= ?
           ORDER BY team_id, match_date DESC""",
        (as_of,),
    ).fetchall()

    # Deduplicate by team_id (keep first = most recent before as_of)
    seen = set()
    result = {}
    for team_id, elo in rows:
        if team_id not in seen:
            seen.add(team_id)
            result[team_id] = elo
    return result


if __name__ == "__main__":
    import sys

    conn = sqlite3.connect(DB_PATH)
    ratings = compute_elo_ratings(conn, save=True)

    # Show top and bottom teams
    sorted_teams = sorted(ratings.items(), key=lambda x: x[1], reverse=True)
    print("\nTop 10 ELO:")
    for team_id, elo in sorted_teams[:10]:
        print(f"  {team_id}: {elo:.1f}")
    print("\nBottom 5 ELO:")
    for team_id, elo in sorted_teams[-5:]:
        print(f"  {team_id}: {elo:.1f}")

    # Verify: Real Madrid > 1700
    rm_elo = ratings.get("real_madrid", 0)
    print(f"\nReal Madrid ELO: {rm_elo:.1f} ({'OK' if rm_elo > 1700 else 'LOW!'})")

    conn.close()
