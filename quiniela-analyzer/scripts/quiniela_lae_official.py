#!/usr/bin/env python3
"""Scraper quiniela oficial de LAE (mirror combinacionganadora.com).

Uso:
    python3 quiniela_lae_official.py --jornada 2026-08-16
"""
import argparse
import sqlite3
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

DB_PATH = Path(__file__).parent.parent / "data" / "quiniela.db"
SOURCE_URL = "https://www.combinacionganadora.com/quiniela/resultados/{date}/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
}


def fetch_official_matches(date_str):
    """Scrape Quiniela oficial. Devuelve lista de partidos."""
    url = SOURCE_URL.format(date=date_str)
    r = requests.get(url, headers=HEADERS, timeout=15)
    r.raise_for_status()
    r.encoding = "utf-8"
    soup = BeautifulSoup(r.text, "html.parser")
    table = None
    for t in soup.find_all("table"):
        rows = t.find_all("tr")
        if rows and len(rows) >= 14:
            table = t
            break
    if not table:
        return []
    matches = []
    pos = 1
    for row in table.find_all("tr"):  # sin skip, primera fila es partido 1
        cells = row.find_all("td")
        if len(cells) < 2:
            continue
        match_cell = cells[1]
        time = cells[2].get_text(strip=True) if len(cells) > 2 else ""
        m1 = match_cell.find("span", attrs={"data-m1": True})
        m2 = match_cell.find("span", attrs={"data-m2": True})
        if m1 and m2:
            home = m1.get_text(strip=True)
            away = m2.get_text(strip=True)
        else:
            match = match_cell.get_text(strip=True).strip()
            if "-" in match:
                home, away = match.split("-", 1)
            else:
                continue
        matches.append({
            "position": pos,
            "home_team": home.strip(),
            "away_team": away.strip(),
            "match_time": time,
        })
        pos += 1
    return matches


def save_to_db(date_str, matches, source="combinacionganadora.com"):
    """Inserta/actualiza partidos oficiales en BD."""
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS lae_quiniela (
            match_date TEXT,
            position INTEGER,
            home_team TEXT,
            away_team TEXT,
            match_time TEXT,
            source TEXT,
            fetched_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (match_date, position)
        )
    """)
    cur.execute("DELETE FROM lae_quiniela WHERE match_date=?", (date_str,))
    for m in matches:
        cur.execute(
            "INSERT INTO lae_quiniela VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
            (date_str, m["position"], m["home_team"],
             m["away_team"], m["match_time"], source),
        )
    conn.commit()
    conn.close()
    return len(matches)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--jornada", required=True, help="YYYY-MM-DD")
    args = parser.parse_args()
    matches = fetch_official_matches(args.jornada)
    if not matches:
        print(f"No se encontraron partidos para {args.jornada}")
        return 1
    n = save_to_db(args.jornada, matches)
    print(f"Jornada {args.jornada}: {n} partidos guardados")
    for m in matches:
        print(f"  {m['position']:2}. {m['home_team']} - {m['away_team']} ({m['match_time']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
