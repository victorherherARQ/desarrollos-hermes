"""Transfermarkt La Liga market value scraper.

Fetches squad size, average age, foreign players, and total squad market value
for all La Liga teams from Transfermarkt.

Market value format examples:
  "€46.92m"   → 46.92 million
  "€560.00m"   → 560.00 million
  "£480.00m"   → 480.00 million (treated as EUR)
  "€12.34k"    → 0.01234 million
"""
from __future__ import annotations

import re
import logging
from dataclasses import dataclass
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

URL = "https://www.transfermarkt.com/laliga/startseite/wettbewerb/ES1"

# Mapping from Transfermarkt club name → canonical team_id
TM_TO_TEAM_ID: dict[str, str] = {
    "Real Madrid":           "real_madrid",
    "FC Barcelona":          "barcelona",
    "Atlético de Madrid":    "atl_madrid",
    "Real Sociedad":         "real_sociedad",
    "Athletic Bilbao":       "ath_bilbao",
    "Villarreal CF":        "villarreal",
    "Sevilla FC":            "sevilla",
    "Real Betis Balompié":  "betis",
    "Valencia CF":           "valencia",
    "Girona FC":             "girona",
    "Getafe CF":             "getafe",
    "CA Osasuna":            "osasuna",
    "Celta de Vigo":         "celta",
    "RCD Mallorca":          "mallorca",
    "Rayo Vallecano":        "rayo_vallecano",
    "Las Palmas":            "las_palmas",
    "CD Leganés":            "leganes",
    "Real Valladolid CF":   "valladolid",
    "RCD Espanyol de Barcelona": "espanyol",
    " Deportivo Alavés":    "alaves",
    "Deportivo Alavés":     "alaves",
    "UD Las Palmas":        "las_palmas",
    " Sevilla FC":           "sevilla",
    # Teams without a current SP1 match but present on the overview page
    "RCD Espanyol Barcelona": "espanol",
    "Levante UD":            "levante",
    "Deportivo A Coruña":    "la_coruna",
    "Racing Santander":     "santander",
    "Elche CF":             "elche",
    "Málaga CF":            "malaga",
}


@dataclass
class TransfermarktTeam:
    tm_name: str          # Name as written on Transfermarkt
    team_id: str | None  # Canonical ID if known, None otherwise
    squad_size: int | None
    average_age: float | None
    foreign_players: int | None
    total_market_value_eur_m: float | None  # Total squad value in EUR millions
    avg_player_value_eur_m: float | None    # Avg player value in EUR millions


def _parse_value(value_str: str) -> float | None:
    """Parse Transfermarkt value string to millions EUR.

    Examples:
        "€560.00m" → 560.0
        "€46.92m"  → 46.92
        "€12.34k"  → 0.01234
        "£480.00m" → 480.0
    """
    if not value_str:
        return None
    value_str = value_str.strip()
    m = re.search(r"([€£$])?\s*([\d.,]+)\s*([mMkK])?", value_str, re.IGNORECASE)
    if not m:
        return None
    num_str = m.group(2).replace(",", ".")
    try:
        num = float(num_str)
    except ValueError:
        return None
    unit = (m.group(3) or "m").upper()
    if unit == "K":
        return num / 1000.0
    return num  # already millions


def fetch_laliga_squads() -> list[TransfermarktTeam]:
    """Scrape Transfermarkt La Liga squads page."""
    teams: list[TransfermarktTeam] = []

    try:
        r = httpx.get(URL, headers=HEADERS, timeout=20)
        r.raise_for_status()
    except httpx.HTTPError as exc:
        logger.error(f"Failed to fetch Transfermarkt: {exc}")
        return []

    soup = BeautifulSoup(r.text, "lxml")
    rows = soup.select("table.items tbody tr")

    if not rows:
        logger.warning(f"No rows found on Transfermarkt page (len={len(r.text)})")
        # Try alternate selectors
        alt_rows = soup.select("tr:nth-of-type(n+2)")
        logger.info(f"Alt rows: {len(alt_rows)}")

    for row in rows:
        cells = row.select("td")
        if len(cells) < 6:
            continue

        tm_name = ""

        # Column layout (index):
        # 0: rank/icon
        # 1: club name + link
        # 2: squad size
        # 3: average age
        # 4: foreign players
        # 5: total market value
        try:
            # Club name — find link inside cell
            name_cell = cells[1]
            name_link = name_cell.select_one("a")
            if name_link:
                tm_name = name_link.text.strip()
            else:
                tm_name = name_cell.text.strip()

            # Remove leading/trailing whitespace
            tm_name = tm_name.strip()

            # Squad size
            squad_text = cells[2].text.strip()
            squad_size = int(squad_text) if squad_text.isdigit() else None

            # Average age
            age_text = cells[3].text.strip().replace(",", ".")
            average_age = float(age_text) if age_text else None

            # Foreign players
            foreign_text = cells[4].text.strip()
            foreign_players = int(foreign_text.split("/")[0]) if "/" in foreign_text else None

            # Market value — look for a link inside the cell (Transfermarkt puts the value in a link)
            value_cell = cells[5]
            value_link = value_cell.select_one("a")
            if value_link:
                value_str = value_link.text.strip()
            else:
                value_str = value_cell.text.strip()

            total_value = _parse_value(value_str)

            # Avg value = what we scraped (avg per player)
            avg_value = total_value
            # Total = avg × squad size
            total_value = (total_value * squad_size) if (total_value is not None and squad_size) else None

            team_id = TM_TO_TEAM_ID.get(tm_name) or TM_TO_TEAM_ID.get(f" {tm_name}")

            if not tm_name or tm_name.strip() == "":
                continue

            teams.append(TransfermarktTeam(
                tm_name=tm_name,
                team_id=team_id,
                squad_size=squad_size,
                average_age=average_age,
                foreign_players=foreign_players,
                total_market_value_eur_m=total_value,
                avg_player_value_eur_m=avg_value,
            ))
            logger.debug(f"  {tm_name}: squad={squad_size}, age={average_age}, value={total_value}")
        except (IndexError, ValueError) as exc:
            logger.warning(f"Error parsing row: {exc}")
            continue

    logger.info(f"Scraped {len(teams)} teams from Transfermarkt")
    return teams


def fetch_individual_squad_value(team_tm_slug: str) -> float | None:
    """Fetch the total squad market value for a specific team.

    team_tm_slug: Transfermarkt URL slug (e.g. 'real-madrid/startseite/verein/4183')
    """
    url = f"https://www.transfermarkt.com/{team_tm_slug}"
    try:
        r = httpx.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "lxml")
        # Look for the market value box
        value_elem = soup.select_one(".tm-value")
        if value_elem:
            return _parse_value(value_elem.text)
        # Try alternate selectors
        for sel in ["[data-market-value]", ".market-value", "#market-value"]:
            elem = soup.select_one(sel)
            if elem:
                return _parse_value(elem.text)
        return None
    except httpx.HTTPError:
        return None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    teams = fetch_laliga_squads()
    for t in teams:
        print(f"{t.tm_name:30s}  id={str(t.team_id):15s}  squad={t.squad_size}  age={t.average_age}  value={t.total_market_value_eur_m}")
