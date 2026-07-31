"""Seed team market value data from Transfermarkt into team_features."""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
from datetime import date, datetime
from pathlib import Path

from src.features.transfermarkt_parser import fetch_laliga_squads

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "quiniela.db"
CACHE_PATH = Path(__file__).resolve().parents[1] / "data" / "raw" / "transfermarkt_seed.json"


def seed_transfermarkt(cache: bool = True) -> dict[str, int]:
    """Fetch from Transfermarkt and upsert into team_features.

    Returns dict with stats: {inserted, updated, skipped, errors}.
    """
    # Load from cache if available
    if cache and CACHE_PATH.exists():
        log.info(f"Loading from cache: {CACHE_PATH}")
        with open(CACHE_PATH) as f:
            data = json.load(f)
        teams = [__import__("src.features.transfermarkt_parser", fromlist=["TransfermarktTeam"]).TransfermarktTeam(**t) for t in data]
    else:
        log.info("Fetching Transfermarkt La Liga squads...")
        teams = fetch_laliga_squads()
        # Cache
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CACHE_PATH, "w") as f:
            json.dump([t.__dict__ for t in teams], f, default=str)
        log.info(f"Cached to {CACHE_PATH}")

    stats = {"inserted": 0, "updated": 0, "skipped": 0, "errors": 0}
    season = "2526"  # current season

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    for team in teams:
        if team.team_id is None:
            log.warning(f"Unknown TM club: '{team.tm_name}', skipping")
            stats["skipped"] += 1
            continue

        # Check if row exists for this team+season
        cur.execute(
            "SELECT 1 FROM team_features WHERE team_id = ? AND season = ?",
            (team.team_id, season),
        )
        exists = cur.fetchone() is not None

        cols = {
            "squad_size": team.squad_size,
            "average_age": team.average_age,
            "foreign_players": team.foreign_players,
            "total_market_value_eur_m": team.total_market_value_eur_m,
            "avg_player_value_eur_m": team.avg_player_value_eur_m,
            "source": "transfermarkt",
            "scraped_at": datetime.utcnow().isoformat(),
            "imputed": 0,
        }
        non_null = {k: v for k, v in cols.items() if v is not None}

        if exists:
            set_clause = ", ".join(f"{k}=?" for k in non_null)
            vals = list(non_null.values()) + [team.team_id, season]
            cur.execute(f"UPDATE team_features SET {set_clause} WHERE team_id=? AND season=?", vals)
            stats["updated"] += 1
            log.info(f"Updated {team.team_id}: total_market={team.total_market_value_eur_m}M EUR")
        else:
            cols.update({"team_id": team.team_id, "season": season})
            all_cols = {k: v for k, v in cols.items() if v is not None}
            names = ", ".join(all_cols.keys())
            placeholders = ", ".join(["?"] * len(all_cols))
            cur.execute(
                f"INSERT INTO team_features ({names}) VALUES ({placeholders})",
                list(all_cols.values()),
            )
            stats["inserted"] += 1
            log.info(f"Inserted {team.team_id}: total_market={team.total_market_value_eur_m}M EUR")

    conn.commit()
    conn.close()
    return stats


def main():
    parser = argparse.ArgumentParser(description="Seed Transfermarkt market value data")
    parser.add_argument("--no-cache", action="store_true", help="Ignore cache and re-scrape")
    args = parser.parse_args()

    stats = seed_transfermarkt(cache=not args.no_cache)
    log.info(f"Done: {stats}")


if __name__ == "__main__":
    main()
