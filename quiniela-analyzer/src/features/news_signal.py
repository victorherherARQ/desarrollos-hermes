"""RSS news scraping for Spanish football teams.

Scrapes headlines from MARCA and Mundo Deportivo RSS feeds,
normalizes team mentions, and stores in `news_signals` table.

DB schema:
    CREATE TABLE news_signals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        team_id TEXT NOT NULL,
        source TEXT NOT NULL,
        headline TEXT NOT NULL,
        pub_date TEXT,
        url TEXT,
        scraped_at TEXT DEFAULT (datetime('now')),
        UNIQUE(team_id, source, headline)
    );
"""
from __future__ import annotations

import re
import sqlite3
import feedparser
import httpx
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "quiniela.db"

# RSS feeds to try
RSS_FEEDS = [
    ("marca", "https://marca.com/rss/futbol/primera-division.xml"),
    ("mundodeportivo", "https://www.mundodeportivo.com/rss/futbol/"),
    ("as", "https://as.com/rss/futbol/primera_division.xml"),
]

# Canonical team_id → list of aliases (case-insensitive matching)
TEAM_ALIASES: dict[str, list[str]] = {
    "real_madrid": ["real madrid", "real madrid cf", "el real", "los blancos", "merengues"],
    "barcelona": ["barcelona", "fc barcelona", "barça", "blaugrana", "el barça"],
    "atl_madrid": ["atlético madrid", "atletico madrid", "atlético", "atleti", "los colchoneros"],
    "sevilla": ["sevilla", "sevilla fc", "sevillistas"],
    "real_betis": ["betis", "real betis", "béticos", "verdiblancos"],
    "athletic_bilbao": ["athletic bilbao", "athletic", "athletic club", "los leones"],
    "real_sociedad": ["real sociedad", "sociedad", "txurdiamak"],
    "villarreal": ["villarreal", "villarreal cf", "el submarino", "submarinos"],
    "valencia": ["valencia", "valencia cf", "los ché", "che", "taronjas"],
    "celta": ["celta", "celta de vigo", "celta vigo", "olívicos"],
    "getafe": ["getafe", "getafe cf", "azulones"],
    "osasuna": ["osasuna", "ca osasuna", "rojos"],
    "mallorca": ["mallorca", "rcd mallorca", "barralet"],
    "espanyol": ["espanyol", "rcd espanyol", "pericos"],
    "las_palmas": ["las palmas", "ud las palmas", "unionista"],
    "alaves": ["alavés", "alaves", "deportivo alavés", "vitorianos"],
    "rayo_vallecano": ["rayo vallecano", "rayo", "los franjirrojos"],
    "betis": ["betis", "real betis"],
    "girona": ["girona", "girona fc"],
    "leganes": ["leganés", "leganes", "cd Leganés"],
    "valladolid": ["valladolid", "real valladolid"],
    "sevilla": ["sevilla", "sevilla fc"],
    "eibar": ["eibar", "sd eibar"],
    "granada": ["granada", "granada cf"],
    "malaga": ["málaga", "malaga", "calichar"],
    "la_coruna": ["deportivo la coruña", "deportivo"],
    "sporting": ["sporting", "sporting de Gijón", "real sporting"],
    "oviedo": ["oviedo", "real oviedo"],
    "huesca": ["huesca", "sd huesca"],
    "almeria": ["almería", "almeria", "ud almería"],
    "cadiz": ["cádiz", "cadiz", "cadíz"],
    "elche": ["elche", "elche cf"],
    "levant": ["levante", "levante ud"],
    "tenerife": ["tenerife", "cd tenerife"],
    "burgos": ["burgos", "cd burgos"],
    "eibar": ["eibar", "sd eibar"],
    "malaga": ["malaga", "málaga cf"],
    "albacete": ["albacete", "albacete balompié"],
    "cartagena": ["cartagena", "fc cartagena"],
    "racing": ["racing", "racing de santander"],
    "castellon": ["castellón", "castellon"],
    "mirandes": ["mirandés", "cd mirandés"],
    "zaragoza": ["zaragoza", "real zaragoza"],
    "deportivo": ["deportivo", "deportivo la coruña"],
}

# Reverse map: alias → team_id (lowercase)
_ALIAS_TO_TEAM: dict[str, str] = {}
for team_id, aliases in TEAM_ALIASES.items():
    for alias in aliases:
        _ALIAS_TO_TEAM[alias.lower()] = team_id


def _match_team(headline: str) -> list[str]:
    """Return list of team_ids mentioned in a headline."""
    matched = set()
    text_lower = headline.lower()
    for alias, team_id in _ALIAS_TO_TEAM.items():
        # word-boundary aware
        pattern = r'\b' + re.escape(alias) + r'\b'
        if re.search(pattern, text_lower):
            matched.add(team_id)
    return list(matched)


def fetch_rss_feed(feed_url: str, source_name: str) -> list[dict]:
    """Parse an RSS feed and return list of {headline, url, pub_date}."""
    try:
        resp = httpx.get(feed_url, timeout=15, follow_redirects=True)
        resp.raise_for_status()
    except Exception as e:
        print(f"  [WARN] Failed to fetch {source_name}: {e}")
        return []

    feed = feedparser.parse(resp.text)
    entries = []
    for entry in feed.entries:
        title = getattr(entry, "title", "") or getattr(entry, "title_detail", None) or ""
        if isinstance(title, dict):
            title = title.get("value", "")
        link = getattr(entry, "link", "") or ""
        pub_str = getattr(entry, "published", "") or getattr(entry, "updated", "") or ""

        # Parse date
        pub_date = ""
        if pub_str:
            try:
                from email.utils import parsedate_to_datetime
                dt = parsedate_to_datetime(pub_str)
                pub_date = dt.isoformat()
            except Exception:
                pass

        entries.append({"headline": title.strip(), "url": link, "pub_date": pub_date})

    return entries


def init_news_signals(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS news_signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_id TEXT NOT NULL,
            source TEXT NOT NULL,
            headline TEXT NOT NULL,
            pub_date TEXT,
            url TEXT,
            scraped_at TEXT DEFAULT (datetime('now')),
            UNIQUE(team_id, source, headline)
        )
    """)
    # Index for fast lookups
    conn.execute("CREATE INDEX IF NOT EXISTS idx_news_team ON news_signals(team_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_news_date ON news_signals(pub_date)")


def store_signals(conn: sqlite3.Connection, source: str, entries: list[dict]) -> int:
    """Store RSS entries, return number of rows inserted."""
    inserted = 0
    for entry in entries:
        teams = _match_team(entry["headline"])
        for team_id in teams:
            try:
                conn.execute(
                    """INSERT OR IGNORE INTO news_signals
                       (team_id, source, headline, pub_date, url) VALUES (?, ?, ?, ?, ?)""",
                    (team_id, source, entry["headline"], entry["pub_date"], entry["url"]),
                )
                inserted += 1
            except Exception:
                pass
    return inserted


def scrape_all_feeds(days_back: int = 7) -> tuple[int, int]:
    """Scrape all configured RSS feeds and store signals.

    Returns (total_entries_found, total_rows_inserted).
    """
    conn = sqlite3.connect(DB_PATH)
    init_news_signals(conn)

    total_entries = 0
    total_inserted = 0

    for source_name, feed_url in RSS_FEEDS:
        print(f"  Fetching {source_name} from {feed_url}")
        entries = fetch_rss_feed(feed_url, source_name)
        total_entries += len(entries)
        inserted = store_signals(conn, source_name, entries)
        total_inserted += inserted
        print(f"    → {len(entries)} headlines, {inserted} team-mention rows stored")

    conn.commit()
    conn.close()
    return total_entries, total_inserted


def get_recent_signals(conn: sqlite3.Connection, team_id: str, days: int = 7) -> list[dict]:
    """Get recent signals for a team within the last N days."""
    since = (datetime.utcnow() - timedelta(days=days)).isoformat()
    rows = conn.execute(
        """SELECT team_id, source, headline, pub_date, url, scraped_at
           FROM news_signals
           WHERE team_id = ? AND pub_date >= ? AND pub_date != ''
           ORDER BY pub_date DESC""",
        (team_id, since),
    ).fetchall()
    cols = [d[0] for d in conn.execute("SELECT * FROM news_signals LIMIT 0").description]
    return [dict(zip(cols, r)) for r in rows]


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Scrape RSS feeds for football news")
    parser.add_argument("--days", type=int, default=7, help="Days back to search (default 7)")
    args = parser.parse_args()

    print(f"[news_signal] Scraping RSS feeds (days_back={args.days})...")
    total_entries, total_inserted = scrape_all_feeds(days_back=args.days)
    print(f"\n✅ Done: {total_entries} headlines, {total_inserted} team-mention rows stored")
