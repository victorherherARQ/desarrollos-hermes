"""Seed football-data closing odds into match_odds table.

Usage:
  python3 scripts/seed_odds.py --seasons 5   # last 5 seasons (default)
  python3 scripts/seed_odds.py --seasons 30  # all available (1993-present)
"""
from __future__ import annotations
import argparse, csv, logging, sqlite3, time
from io import StringIO
from pathlib import Path
import httpx
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-GB,en;q=0.9",
}
BASE_URL = "https://www.football-data.co.uk"

FD2ID: dict[str, str] = {
    "alaves": "alaves", "athletic bilbao": "ath_bilbao", "ath bilbao": "ath_bilbao",
    "atletico madrid": "atl_madrid", "atl madrid": "atl_madrid",
    "barcelona": "barcelona", "betis": "betis", "celta": "celta",
    "cordoba": "cordoba", "deportivo": "la_coruna",
    "eibar": "eibar", "espanol": "espanol", "espanyol": "espanol",
    "getafe": "getafe", "girona": "girona", "granada": "granada",
    "hercules": "hercules", "huesca": "huesca",
    "la coruna": "la_coruna", "las palmas": "las_palmas",
    "leganes": "leganes", "legan": "leganes", "levante": "levante",
    "malaga": "malaga", "mallorca": "mallorca",
    "osasuna": "osasuna", "oviedo": "oviedo",
    "racing santander": "santander", "rayo vallecano": "vallecano", "rayo": "vallecano",
    "real madrid": "real_madrid", "real sociedad": "sociedad", "sociedad": "sociedad",
    "sevilla": "sevilla", "gijon": "sp_gijon", "sp. gijon": "sp_gijon", "sp gijon": "sp_gijon",
    "valencia": "valencia", "valladolid": "valladolid", "villarreal": "villarreal",
    "xerez": "xerez", "zaragoza": "zaragoza",
    "albacete": "albacete", "alcorcon": "alcorcon", "alcoyano": "alcoyano",
    "almeria": "almeria", "amorebieta": "amorebieta", "andorra": "andorra",
    "barcelona b": "barcelona_b", "burgos": "burgos", "cadiz": "cadiz",
    "cartagena": "cartagena", "castellon": "castellon", "ceuta": "ceuta",
    "cultural leonesa": "cultural_leonesa", "eldense": "eldense",
    "extremadura": "extremadura_ud", "ferrol": "ferrol", "fuenlabrada": "fuenlabrada",
    "gimnastic": "gimnastic", "gimnastic tarragona": "gimnastic",
    "guadalajara": "guadalajara", "ibiza": "ibiza", "jaen": "jaen",
    "lleida": "lleida", "llagostera": "llagostera", "logrones": "logrones",
    "lorca": "lorca", "lugo": "lugo", "mirandes": "mirandes",
    "murcia": "murcia", "numancia": "numancia", "ponferradina": "ponferradina",
    "rayo majadahonda": "rayo_majadahonda", "recreativo": "recreativo",
    "reus": "reus_deportiu", "sabadell": "sabadell", "salamanca": "salamanca",
    "santander": "santander", "tenerife": "tenerife",
    "ucam murcia": "ucam_murcia", "villarreal b": "villarreal_b",
}

ODDS_COLS = [
    "match_id", "season", "division", "matchday_date", "home_team", "away_team",
    "home_goals", "away_goals", "result",
    "avg_h", "avg_d", "avg_a", "max_h", "max_d", "max_a",
    "psc_h", "psc_d", "psc_a", "b365c_h", "b365c_d", "b365c_a",
    "avg_c_h", "avg_c_d", "avg_c_a",
    "imp_h", "imp_d", "imp_a", "imp_c_h", "imp_c_d", "imp_c_a",
    "hs", "away_shots", "hst", "ast",
    "hf", "af", "hc", "ac", "hy", "ay", "hr", "ar",
    "hthg", "htag", "htr",
    "source_url",
]

INSERT_SQL = f"INSERT OR IGNORE INTO match_odds ({', '.join(ODDS_COLS)}) VALUES ({', '.join(['?'] * len(ODDS_COLS))})"


def fd_year(code: str) -> int:
    y1 = int(code[:2])
    return 1900 + y1 if y1 > 50 else 2000 + y1


def parse_date(s: str) -> str:
    d, m, y = s.strip().split("/")
    d, m, y = int(d), int(m), int(y)
    if y < 100:
        y = 1900 + y if y > 50 else 2000 + y
    return f"{y:04d}-{m:02d}-{d:02d}"


def fl(s: str):
    try:
        return float(s.strip()) if s.strip() else None
    except Exception:
        return None


def it(s: str):
    try:
        return int(s.strip()) if s.strip() else None
    except Exception:
        return None


def implied(h, d, a):
    if not (h and d and a):
        return None, None, None
    t = 1 / h + 1 / d + 1 / a
    if t <= 0 or t > 1000:
        return None, None, None
    return 1 / h / t, 1 / d / t, 1 / a / t


def run(seasons: int = 5) -> int:
    DB = Path(__file__).parent.parent / "data" / "quiniela.db"
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    cur.execute("DROP TABLE IF EXISTS match_odds")
    cur.execute(f"""
        CREATE TABLE match_odds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            match_id INTEGER,
            season TEXT,
            division TEXT,
            matchday_date DATE,
            home_team TEXT,
            away_team TEXT,
            home_goals INTEGER,
            away_goals INTEGER,
            result TEXT,
            hthg INTEGER, htag INTEGER, htr TEXT,
            hs INTEGER, away_shots INTEGER, hst INTEGER, ast INTEGER,
            hf INTEGER, af INTEGER, hc INTEGER, ac INTEGER,
            hy INTEGER, ay INTEGER, hr INTEGER, ar INTEGER,
            avg_h REAL, avg_d REAL, avg_a REAL,
            max_h REAL, max_d REAL, max_a REAL,
            psc_h REAL, psc_d REAL, psc_a REAL,
            b365c_h REAL, b365c_d REAL, b365c_a REAL,
            avg_c_h REAL, avg_c_d REAL, avg_c_a REAL,
            imp_h REAL, imp_d REAL, imp_a REAL,
            imp_c_h REAL, imp_c_d REAL, imp_c_a REAL,
            source_url TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (match_id) REFERENCES matches(match_id),
            UNIQUE (season, division, matchday_date, home_team, away_team)
        )
    """)
    conn.commit()

    # Build match_id lookup: key -> match_id
    match_ids: dict[tuple, int] = {}
    for (mid, s, d, hd, ad, dt) in cur.execute(
        "SELECT match_id, season, division, home_team, away_team, matchday_date FROM matches"
    ).fetchall():
        key = (str(s), str(d), str(hd).lower(), str(ad).lower(), str(dt)[:10])
        match_ids[key] = mid
    log.info(f"Match IDs loaded: {len(match_ids)}")

    # Get CSV URLs
    r = httpx.get(f"{BASE_URL}/spainm.php", headers=HEADERS, timeout=15)
    soup = BeautifulSoup(r.text, "lxml")
    links: list[tuple] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.endswith(".csv"):
            parts = href.split("/")
            season_code = parts[1]
            div = parts[2].replace(".csv", "").upper()
            links.append((fd_year(season_code), season_code, div, f"{BASE_URL}/{href}"))

    links.sort(key=lambda x: x[0], reverse=True)
    recent = links[: seasons * 2]
    log.info(f"Seasons: {[l[1] for l in recent]}")

    total = 0
    client = httpx.Client(headers=HEADERS, timeout=30)
    for year, season_code, div, url in recent:
        r = client.get(url)
        rows = list(csv.DictReader(StringIO(r.text)))
        inserted = 0
        for rec in rows:
            ht = rec.get("HomeTeam", "").strip().lower()
            at = rec.get("AwayTeam", "").strip().lower()
            ht_id = FD2ID.get(ht)
            at_id = FD2ID.get(at)
            if not ht_id or not at_id:
                continue
            dt = parse_date(rec.get("Date", ""))
            key = (season_code, div, ht_id, at_id, dt)
            match_id = match_ids.get(key)
            if not match_id:
                continue

            fthg = it(rec.get("FTHG", ""))
            ftag = it(rec.get("FTAG", ""))
            ftr = rec.get("FTR", "").strip() or None
            avg_h = fl(rec.get("AvgH", ""))
            avg_d = fl(rec.get("AvgD", ""))
            avg_a = fl(rec.get("AvgA", ""))
            max_h = fl(rec.get("MaxH", ""))
            max_d = fl(rec.get("MaxD", ""))
            max_a = fl(rec.get("MaxA", ""))
            psc_h = fl(rec.get("PSCH", ""))
            psc_d = fl(rec.get("PSCD", ""))
            psc_a = fl(rec.get("PSA", ""))
            b365c_h = fl(rec.get("B365CH", ""))
            b365c_d = fl(rec.get("B365CD", ""))
            b365c_a = fl(rec.get("B365CA", ""))
            avg_c_h = fl(rec.get("AvgCH", ""))
            avg_c_d = fl(rec.get("AvgCD", ""))
            avg_c_a = fl(rec.get("AvgCA", ""))
            ih, id_, ia = implied(avg_h, avg_d, avg_a) if avg_h else (None, None, None)
            ich, icd, ica = implied(avg_c_h, avg_c_d, avg_c_a) if avg_c_h else (None, None, None)

            vals = [
                match_id,
                season_code, div, dt, ht_id, at_id,
                fthg, ftag, ftr,
                avg_h, avg_d, avg_a, max_h, max_d, max_a,
                psc_h, psc_d, psc_a, b365c_h, b365c_d, b365c_a,
                avg_c_h, avg_c_d, avg_c_a,
                ih, id_, ia, ich, icd, ica,
                it(rec.get("HS", "")), it(rec.get("AS", "")),
                it(rec.get("HST", "")), it(rec.get("AST", "")),
                it(rec.get("HF", "")), it(rec.get("AF", "")),
                it(rec.get("HC", "")), it(rec.get("AC", "")),
                it(rec.get("HY", "")), it(rec.get("AY", "")),
                it(rec.get("HR", "")), it(rec.get("AR", "")),
                it(rec.get("HTHG", "")), it(rec.get("HTAG", "")),
                rec.get("HTR", "").strip() or None,
                url,
            ]

            if len(vals) != len(ODDS_COLS):
                log.warning(f"Row {key}: {len(vals)} vals for {len(ODDS_COLS)} cols — skipping")
                continue

            cur.execute(INSERT_SQL, vals)
            if cur.rowcount:
                inserted += 1

        conn.commit()
        total += inserted
        log.info(f"{season_code} {div}: {inserted}/{len(rows)} rows inserted")
        time.sleep(0.5)

    client.close()
    conn.close()
    log.info(f"Done! Total: {total} rows")

    conn2 = sqlite3.connect(DB)
    cur2 = conn2.cursor()
    total_rows = cur2.execute("SELECT COUNT(*) FROM match_odds").fetchone()[0]
    with_imp = cur2.execute("SELECT COUNT(*) FROM match_odds WHERE imp_h IS NOT NULL").fetchone()[0]
    by_season = cur2.execute(
        "SELECT season, COUNT(*) FROM match_odds GROUP BY season ORDER BY season DESC"
    ).fetchall()
    log.info(f"Total: {total_rows}, with implied probs: {with_imp}")
    for row in by_season:
        log.info(f"  {row}")
    conn2.close()
    return total


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Seed football-data closing odds")
    p.add_argument("--seasons", type=int, default=5, help="Number of recent seasons (default: 5)")
    run(p.parse_args().seasons)
