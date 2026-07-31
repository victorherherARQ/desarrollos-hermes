#!/usr/bin/env python3
"""Seed news signals from RSS feeds.
Usage: python scripts/seed_news_signals.py --days 7
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.features.news_signal import scrape_all_feeds

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=7)
    args = parser.parse_args()

    print(f"Scraping RSS feeds for the last {args.days} days...")
    total_entries, total_inserted = scrape_all_feeds(days_back=args.days)
    print(f"\n✅ Done — {total_entries} headlines found, {total_inserted} team-mention rows inserted")
