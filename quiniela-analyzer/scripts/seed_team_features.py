#!/usr/bin/env python3
"""Seed team_features table from Wikipedia scraping."""
import argparse
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.features.team_value import seed_all_teams, DB_PATH
import sqlite3


def main():
    parser = argparse.ArgumentParser(description="Seed team_features from Wikipedia")
    parser.add_argument("--season", default="2526", help="Season code (e.g. 2526)")
    parser.add_argument("--no-cache", action="store_true", help="Skip cache, re-scrape")
    args = parser.parse_args()

    print(f"Scraping Wikipedia for season {args.season}...")
    data = seed_all_teams(season=args.season, use_cache=not args.no_cache)

    # Summary
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM team_features WHERE season = ?", (args.season,))
    total = cur.fetchone()[0]
    cur.execute(
        "SELECT COUNT(*) FROM team_features WHERE season = ? AND imputed = 0",
        (args.season,),
    )
    real = cur.fetchone()[0]
    print(f"\n✓ team_features table: {total} rows ({real} real, {total - real} imputed)")

    # Show sample
    rows = cur.execute(
        "SELECT team_id, manager, stadium_capacity, budget_millions, market_value_millions "
        "FROM team_features WHERE season = ? LIMIT 10",
        (args.season,),
    ).fetchall()
    print("\nSample (first 10):")
    for r in rows:
        print(f"  {r[0]}: manager={r[1]}, capacity={r[2]}, budget={r[3]}, value={r[4]}")

    conn.close()


if __name__ == "__main__":
    main()
