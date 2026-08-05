"""Descarga xG de StatsBomb open data para LaLiga.

StatsBomb open data: github.com/statsbomb/open-data
LaLiga (comp_id=11) temporadas 21,22,23,24,25,26,27,1,2,4,42,90 = ~758 partidos.

Por cada partido descarga events.json y extrae shots con statsbomb_xg.

Output: tabla statsbomb_xg_match con match_id_statsbomb, home_team_name,
away_team_name, match_date, home_xg_sum, away_xg_sum.
"""
import json
import logging
import sqlite3
import time
from pathlib import Path

import httpx
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "quiniela.db"
STATSBOMB_BASE = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)

LA_LIGA_SEASON_IDS = [21, 22, 23, 24, 25, 26, 27, 1, 2, 4, 42, 90]


def download_matches(client: httpx.Client, season_id: int) -> list:
    url = f"{STATSBOMB_BASE}/matches/11/{season_id}.json"
    try:
        r = client.get(url, timeout=15)
        if r.status_code == 200:
            return json.loads(r.text)
        log.warning(f"season_id={season_id} → {r.status_code}")
    except Exception as e:
        log.warning(f"season_id={season_id} ERROR: {e}")
    return []


def compute_match_xg(client: httpx.Client, match_id: int) -> tuple:
    """Devuelve (home_xg, away_xg) de los shots del partido."""
    url = f"{STATSBOMB_BASE}/events/{match_id}.json"
    try:
        r = client.get(url, timeout=30)
        if r.status_code != 200:
            return None, None
        events = json.loads(r.text)
    except Exception as e:
        log.warning(f"events match {match_id} ERROR: {e}")
        return None, None

    home_team_id = None
    home_xg = 0.0
    away_xg = 0.0

    for ev in events:
        if ev.get("type", {}).get("name") != "Shot":
            continue
        if ev.get("team", {}).get("id") and home_team_id is None:
            home_team_id = ev["team"]["id"]
        xg = ev.get("shot", {}).get("statsbomb_xg", 0.0) or 0.0
        if ev.get("team", {}).get("id") == home_team_id:
            home_xg += xg
        else:
            away_xg += xg

    return home_xg, away_xg


def main():
    client = httpx.Client(headers={"User-Agent": "Mozilla/5.0"})
    rows = []

    total = 0
    for sid in LA_LIGA_SEASON_IDS:
        matches = download_matches(client, sid)
        log.info(f"Season {sid}: {len(matches)} partidos")
        for m in matches:
            mid = m["match_id"]
            home_xg, away_xg = compute_match_xg(client, mid)
            if home_xg is None:
                continue
            rows.append({
                "statsbomb_match_id": mid,
                "home_team_name": m["home_team"]["home_team_name"],
                "away_team_name": m["away_team"]["away_team_name"],
                "match_date": m["match_date"],
                "season_id": sid,
                "home_xg": home_xg,
                "away_xg": away_xg,
            })
            total += 1
            if total % 50 == 0:
                log.info(f"  {total} partidos procesados...")

    log.info(f"Total StatsBomb xG: {total} partidos")
    df = pd.DataFrame(rows)
    df["match_date"] = pd.to_datetime(df["match_date"])

    conn = sqlite3.connect(DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS statsbomb_xg_matches (
            statsbomb_match_id INTEGER PRIMARY KEY,
            home_team_name TEXT,
            away_team_name TEXT,
            match_date TEXT,
            season_id INTEGER,
            home_xg REAL,
            away_xg REAL
        )
    """)
    conn.execute("DELETE FROM statsbomb_xg_matches")
    conn.commit()
    df.to_sql("statsbomb_xg_matches", conn, if_exists="append", index=False)

    n = conn.execute("SELECT COUNT(*) FROM statsbomb_xg_matches").fetchone()[0]
    log.info(f"✅ statsbomb_xg_matches: {n} filas")

    log.info("\nTop 5 partidos por xG_home:")
    top = conn.execute("SELECT home_team_name, away_team_name, home_xg, away_xg FROM statsbomb_xg_matches ORDER BY home_xg DESC LIMIT 5").fetchall()
    for r in top:
        log.info(f"  {r[0]} vs {r[1]}: {r[2]:.2f} - {r[3]:.2f}")

    conn.close()


if __name__ == "__main__":
    main()