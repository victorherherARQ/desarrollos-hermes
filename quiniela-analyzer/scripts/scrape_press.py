"""Press scraper — Marca, AS, Mundo Deportivo RSS feeds.

Covers: La Liga Primera División + Segunda División news.
Each run fetches latest articles and stores in press_articles table.
"""
from __future__ import annotations
import argparse, feedparser, logging, sqlite3, time, re
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; HermesBot/1.0; +https://hermes)",
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}

FEEDS = {
    "marca_sp1": "https://www.marca.com/rss/futbol/primera-division.xml",
    "marca_sp2": "https://www.marca.com/rss/futbol/segunda-division.xml",
    "marca_euro": "https://www.marca.com/rss/futbol/champions-league.xml",
    "marca_eur":  "https://www.marca.com/rss/futbol/europa-league.xml",
}

TEAM_PATTERNS: dict[str, list[str]] = {
    "real_madrid": ["real madrid", "rm", "merengues", "blancos"],
    "barcelona":   ["barça", "barcelona", "fc barcelona", "culers"],
    "atl_madrid":  ["atletico", "atlético", "colchoneros", "atl madrid"],
    "sevilla":     ["sevilla", "sevillistas"],
    "betis":       ["betis", "real betis", "heliopolitanos"],
    "sociedad":    ["real sociedad", "txuri-urdin", "manolo"],
    "villarreal":  ["villarreal", "groguets", "submarino"],
    "ath_bilbao":  ["athletic", "athletic bilbao", "los leones", "ath bilbao"],
    "valencia":    ["valencia cf", "valencia"],
    "getafe":      ["getafe"],
    "girona":      ["girona"],
    "las_palmas":  ["las palmas", "ud las palmas"],
    "mallorca":    ["mallorca"],
    "osasuna":     ["osasuna"],
    "alaves":      ["alavés", "deportivo alavés", "alaves"],
    "celta":       ["celta", "celta de vigo"],
    "espanyol":    ["espanyol", "rcd espanyol"],
    "vallecano":   ["rayo vallecano", "rayo"],
    "levante":     ["levante ud", "levante"],
    "leganes":     ["leganés", "leganes"],
    "eibar":       ["eibar", "sd eibar"],
    "malaga":      ["málaga", "malaga", "califa"],
    "granada":     ["granada cf", "granada"],
    "deportivo":   ["deportivo", "deportivo la Coruña", "deportivo coruna", "deportivo de la Coruña", "deportivo de coruña", "rc depor"],
    "zaragoza":    ["zaragoza", "real zaragoza"],
    "valladolid":  ["valladolid", "real valladolid", "pucela"],
    "huesca":      ["huesca", "sd huesca"],
    "tenerife":    ["tenerife", "cd tenerife"],
    "lugo":        ["lugo", "cd lugo"],
    "oviedo":      ["oviedo", "real oviedo"],
    "almeria":     ["almería", "almeria", "ud almería"],
    "cordoba":     ["córdoba", "cordoba"],
    "cartagena":   ["cartagena", "fc cartagena"],
    "mirandes":    ["mirandés", "mirandes", "cd mirandés"],
    "cadiz":       ["cádiz", "cadiz", "rácano"],
    "eibar":       ["eibar", "sd eibar", "armero"],
    "albacete":    ["albacete", "albacete bp"],
    "castellon":   ["castellón", "castellon"],
    "gimnastic":   ["gimnàstic", "gimnastic", "tarragona"],
}

POSITIVE = [
    "victoria", "ganar", "gana", "ganador", "triunfo", "título", "titulo",
    "campeón", "campeon", "lider", "líder", "oro", "brillo", "goleada",
    "hermoso", "increíble", "increible", "espectacular", "milagro",
    "renovación", "renovacion", "fichaje", "contrato", "estrella",
    "asciende", "ascenso", "prometedor", "éxito", "exito", "apuesta",
    "golazo", "hat-trick", "hattrick", "pichichi", "zamarra",
    "revolución", "revolucion", "explosión", "explosion",
]
NEGATIVE = [
    "derrota", "pierde", "perder", "fracaso", "caer", "caída", "caida",
    "crisis", "alarma", "emergencia", "tragedia", "desastre", "batacazo",
    "vergüenza", "verguenza", "pésimo", "pesimo", "desastroz",
    "lesión", "lesion", "lesionado", "sancion", "sanción", "expulsado",
    "cese", "destitución", "destitucion", "despido", "baja",
    "escándalo", "escandalo", "polémica", "polemica", "decepcion",
    "duda", "incertidumbre", "complicado", "difícil", "dificil",
]


def normalize(text: str) -> str:
    return text.lower().strip()


def extract_teams(text: str) -> set[str]:
    text_lower = normalize(text)
    found = set()
    for team, patterns in TEAM_PATTERNS.items():
        for pat in patterns:
            if pat in text_lower:
                found.add(team)
                break
    return found


def sentiment_score(text: str) -> float:
    text_lower = normalize(text)
    pos = sum(1 for w in POSITIVE if w in text_lower)
    neg = sum(1 for w in NEGATIVE if w in text_lower)
    total = pos + neg
    if total == 0:
        return 0.0
    return (pos - neg) / total  # range [-1, +1]


def parse_date_rss(raw: str) -> str | None:
    for fmt in ["%a, %d %b %Y %H:%M:%S %z", "%Y-%m-%dT%H:%M:%S%z",
                "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"]:
        for tz in ["", " +0000", " +0100", " +0200"]:
            try:
                return datetime.strptime(raw.strip() + tz, fmt).strftime("%Y-%m-%d")
            except Exception:
                pass
    # fallback: try to extract date with regex
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", raw)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return None


def fetch_feed(name: str, url: str, since_days: int = 30) -> list[dict]:
    client = httpx.Client(headers=HEADERS, timeout=15)
    try:
        r = client.get(url)
        if r.status_code != 200:
            log.warning(f"[{name}] HTTP {r.status_code}")
            return []
        fp = feedparser.parse(r.text)
        cutoff = (date.today() - timedelta(days=since_days)).isoformat()
        articles = []
        for entry in fp.entries:
            pub = parse_date_rss(entry.get("published", ""))
            if not pub or pub < cutoff:
                continue
            title = entry.get("title", "").strip()
            summary = entry.get("summary", "").strip()
            link = entry.get("link", "")
            if not title:
                continue
            teams = extract_teams(title + " " + summary)
            score = sentiment_score(title + " " + summary)
            articles.append({
                "feed": name,
                "published": pub,
                "title": title[:500],
                "summary": summary[:2000],
                "link": link,
                "teams": teams,
                "sentiment": score,
            })
        log.info(f"[{name}] {len(articles)}/{len(fp.entries)} articles in window")
        return articles
    except Exception as e:
        log.error(f"[{name}] Error: {e}")
        return []
    finally:
        client.close()


def init_db(conn: sqlite3.Connection):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS press_articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            feed TEXT,
            published DATE,
            title TEXT,
            summary TEXT,
            link TEXT,
            teams TEXT,   -- JSON array of team_ids
            sentiment REAL,
            created_at TEXT DEFAULT (datetime('now')),
            UNIQUE (feed, published, title)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS press_signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_id TEXT,
            signal_date DATE,
            article_count INTEGER,
            avg_sentiment REAL,
            headline_examples TEXT,
            source TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            UNIQUE (team_id, signal_date),
            FOREIGN KEY (team_id) REFERENCES teams(team_id)
        )
    """)
    conn.commit()


def store_articles(conn: sqlite3.Connection, articles: list[dict]) -> int:
    import json
    inserted = 0
    for art in articles:
        try:
            cur = conn.execute("""
                INSERT OR IGNORE INTO press_articles
                (feed, published, title, summary, link, teams, sentiment)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (art["feed"], art["published"], art["title"], art["summary"],
                  art["link"], json.dumps(sorted(art["teams"])), art["sentiment"]))
            if cur.rowcount:
                inserted += 1
        except Exception as e:
            log.debug(f"Skip article: {e}")
    conn.commit()
    return inserted


def aggregate_signals(conn: sqlite3.Connection, since_days: int = 7) -> int:
    import json
    cutoff = (date.today() - timedelta(days=since_days)).isoformat()
    rows = conn.execute("""
        SELECT published, teams, sentiment FROM press_articles
        WHERE published >= ?
    """, (cutoff,)).fetchall()

    team_stats: dict[str, dict] = {}
    for pub, teams_json, sent in rows:
        teams = json.loads(teams_json) if teams_json else []
        for team_id in teams:
            if team_id not in team_stats:
                team_stats[team_id] = {"count": 0, "sentiment_sum": 0.0, "headlines": []}
            team_stats[team_id]["count"] += 1
            team_stats[team_id]["sentiment_sum"] += (sent or 0)
            if sent and abs(sent) >= 0.5:
                team_stats[team_id]["headlines"].append(sent)

    today = date.today().isoformat()
    inserted = 0
    for team_id, stats in team_stats.items():
        n = stats["count"]
        avg_s = stats["sentiment_sum"] / n if n > 0 else 0.0
        headlines = ",".join(str(h) for h in stats["headlines"][:5])
        try:
            cur = conn.execute("""
                INSERT OR REPLACE INTO press_signals
                (team_id, signal_date, article_count, avg_sentiment, headline_examples, source)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (team_id, today, n, avg_s, headlines, "marca_rss"))
            if cur.rowcount:
                inserted += 1
        except Exception as e:
            log.debug(f"Skip signal for {team_id}: {e}")
    conn.commit()
    return inserted


def run(since_days: int = 7, dry_run: bool = False) -> dict:
    DB = Path(__file__).parent.parent / "data" / "quiniela.db"
    conn = sqlite3.connect(DB)
    init_db(conn)

    total_articles = 0
    article_details = []

    for name, url in FEEDS.items():
        articles = fetch_feed(name, url, since_days)
        article_details.extend(articles)
        if not dry_run:
            n = store_articles(conn, articles)
            total_articles += n
        time.sleep(0.5)

    signals = 0
    if not dry_run:
        signals = aggregate_signals(conn)

    conn.close()

    # Summary
    import json
    summary = {
        "date": date.today().isoformat(),
        "feeds": list(FEEDS.keys()),
        "articles_fetched": len(article_details),
        "articles_stored": total_articles,
        "signals_aggregated": signals,
        "teams_mentioned": list(set(
            t for a in article_details for t in a["teams"]
        )),
    }
    log.info(f"Done: {total_articles} stored, {signals} signals aggregated")
    if article_details:
        log.info("Sample articles:")
        for a in article_details[:5]:
            log.info(f"  [{a['published']}] {a['title'][:80]} — teams: {sorted(a['teams'])}")
    return summary


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Scrape press RSS and store signals")
    p.add_argument("--days", type=int, default=7, help="Days to look back (default: 7)")
    p.add_argument("--dry-run", action="store_true", help="Fetch but don't store")
    args = p.parse_args()
    import json
    result = run(args.days, args.dry_run)
    print(json.dumps(result, indent=2))
