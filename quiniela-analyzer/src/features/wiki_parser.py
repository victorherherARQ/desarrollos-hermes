"""Wikipedia parser for La Liga team information.

Scrapes:
- https://en.wikipedia.org/wiki/2025%E2%80%9326_La_Liga (stadiums, capacity, personnel)
- Individual team pages for budget, market value, squad size
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

import httpx
from bs4 import BeautifulSoup

WIKI_BASE = "https://en.wikipedia.org/wiki"
LALIGA_URL = f"{WIKI_BASE}/2025%E2%80%9326_La_Liga"
SEGUNDA_URL = f"{WIKI_BASE}/2025%E2%80%9326_Segunda_Divisi%C3%B3n"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; quiniela-analyzer/1.0; research)"
}


@dataclass
class TeamWikiData:
    team_id: str
    team_name: str
    season: str
    # Stadium info
    stadium: Optional[str] = None
    stadium_capacity: Optional[int] = None
    # Personnel
    manager: Optional[str] = None
    captain: Optional[str] = None
    kit_brand: Optional[str] = None
    # Financial
    budget_millions: Optional[float] = None
    market_value_millions: Optional[float] = None
    squad_size: Optional[int] = None
    # Metadata
    source_url: Optional[str] = None
    scraped_at: Optional[str] = None
    missing_fields: list[str] = None

    def __post_init__(self):
        if self.missing_fields is None:
            self.missing_fields = []


def _get(client: httpx.Client, url: str, retries: int = 3) -> Optional[BeautifulSoup]:
    """Fetch a Wikipedia page with retries."""
    for attempt in range(retries):
        try:
            resp = client.get(url, headers=HEADERS, timeout=15)
            if resp.status_code == 200:
                return BeautifulSoup(resp.text, "lxml")
            elif resp.status_code == 404:
                return None
        except Exception:
            if attempt < retries - 1:
                time.sleep(1)
    return None


def _parse_capacity(text: Optional[str]) -> Optional[int]:
    """Extract capacity number from text like 'Capacity: 60,000'."""
    if not text:
        return None
    m = re.search(r"[\d,]+", text.replace(",", ""))
    if m:
        return int(m.group().replace(",", ""))
    return None


def _parse_millions(text: Optional[str]) -> Optional[float]:
    """Extract budget/value in millions from text like '€675m', '675 million', or '212000000'.

    If the number is very large (>10000) and has no unit, assume it's in euros
    (not millions) and convert to millions.
    """
    if not text:
        return None
    text = text.replace(",", "").lower()
    m = re.search(r"([\d.]+)\s*(m|million|€|eur)?", text)
    if m:
        val = float(m.group(1))
        unit = m.group(2) or ""
        # If unit is million/euro symbol or no unit but small number → as-is
        # If no unit but large number → likely raw euros, divide by 1M
        if not unit and val > 10000:
            val = val / 1_000_000.0
        return val
    return None


def scrape_laliga_overview(client: httpx.Client, season: str = "2526") -> dict[str, dict]:
    """Scrape the main La Liga season page for stadium/personnel data."""
    soup = _get(client, LALIGA_URL)
    if not soup:
        return {}

    result = {}

    # Try to find "Stadiums and locations" table
    tables = soup.find_all("table", class_="wikitable")
    for table in tables:
        # Check header
        headers = [th.get_text(strip=True).lower() for th in table.find_all("th")]
        if any("stadium" in h or "location" in h for h in headers):
            rows = table.find_all("tr")
            for row in rows[1:]:  # skip header
                cells = [td.get_text(strip=True) for td in row.find_all(["td", "th"])]
                if len(cells) < 3:
                    continue
                # Team name usually in first cell
                team_name = cells[0]
                # Stadium capacity in one of the cells
                for cell in cells:
                    cap = _parse_capacity(cell)
                    if cap and cap > 5000:
                        result[team_name.lower()] = {
                            "stadium": team_name,
                            "stadium_capacity": cap,
                        }
                        break

    # Try "Personnel and kits" table
    for table in soup.find_all("table", class_="wikitable"):
        headers = [th.get_text(strip=True).lower() for th in table.find_all("th")]
        if any("personnel" in h or "kit" in h for h in headers):
            rows = table.find_all("tr")
            for row in rows[1:]:
                cells = [td.get_text(strip=True) for td in row.find_all(["td", "th"])]
                if len(cells) < 4:
                    continue
                team_name = cells[0]
                # manager, captain, kit, sponsor in subsequent cells
                if team_name.lower() in result:
                    result[team_name.lower()]["manager"] = cells[1] if len(cells) > 1 else None
                    result[team_name.lower()]["kit_brand"] = cells[3] if len(cells) > 3 else None

    return result


def scrape_team_page(client: httpx.Client, team_slug: str, team_name: str) -> Optional[TeamWikiData]:
    """Scrape individual Wikipedia page for a team."""
    url = f"{WIKI_BASE}/{team_slug.replace(' ', '_')}"
    soup = _get(client, url)
    if not soup:
        return None

    from datetime import datetime
    now = datetime.utcnow().isoformat()

    # Use _slugify to ensure consistent team_id with repository
    tid = _slugify(team_name)

    data = TeamWikiData(
        team_id=tid,
        team_name=team_name,
        season="2526",
        source_url=url,
        scraped_at=now,
    )

    # Parse infobox
    infobox = soup.find("table", class_="infobox")
    if infobox:
        rows = infobox.find_all("tr")
        for row in rows:
            label = row.find("th")
            value = row.find("td")
            if not label or not value:
                continue
            label_text = label.get_text(strip=True).lower()
            value_text = value.get_text(separator=" ", strip=True)

            if "capacity" in label_text:
                data.stadium_capacity = _parse_capacity(value_text)
            elif "manager" in label_text or "head coach" in label_text:
                data.manager = value_text
            elif "captain" in label_text:
                data.captain = value_text
            elif "kit" in label_text:
                data.kit_brand = value_text
            elif "budget" in label_text:
                data.budget_millions = _parse_millions(value_text)
            elif "market value" in label_text:
                data.market_value_millions = _parse_millions(value_text)
            elif "squad" in label_text:
                m = re.search(r"\d+", value_text)
                if m:
                    data.squad_size = int(m.group())

    # Track missing fields
    for field in ["budget_millions", "market_value_millions", "stadium_capacity", "manager", "squad_size"]:
        if getattr(data, field) is None:
            data.missing_fields.append(field)

    return data


def _slugify(name: str) -> str:
    """Stable, lowercase, ASCII-ish slug matching repository.team_id."""
    s = name.lower()
    replacements = {
        "á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u",
        "à": "a", "è": "e", "ì": "i", "ò": "o", "ù": "u",
        "ñ": "n", "ç": "c",
    }
    for a, b in replacements.items():
        s = s.replace(a, b)
    s = s.replace("'", "")
    s = s.replace("-", " ")
    out = []
    for token in s.split():
        token = token.strip(".,()")
        if token:
            out.append(token)
    return "_".join(out) or "unknown"


# Mapping from Wikipedia team names (as found on Wikipedia pages) to canonical
# football-data team_ids (from teams table). This ensures join compatibility.
WIKI_TO_TEAM_ID: dict[str, str] = {
    "Athletic Club": "ath_bilbao",
    "Athletic Bilbao": "ath_bilbao",
    "Club Atlético de Madrid": "ath_madrid",
    "Atlético Madrid": "ath_madrid",
    "Real Betis": "betis",
    "RCD Espanyol": "espanol",
    "Espanyol": "espanol",
    "Real Sociedad": "sociedad",
    "Rayo Vallecano": "vallecano",
    "RCD Mallorca": "mallorca",
    "RC Celta de Vigo": "celta",
    "Celta Vigo": "celta",
    "Villarreal CF": "villarreal",
    "Real Valladolid": "valladolid",
    "CA Osasuna": "osasuna",
    "UD Las Palmas": "las_palmas",
    "CD Leganés": "leganes",
    "Deportivo Alavés": "alaves",
    "Alavés": "alaves",
    "Racing Club de Santander": "racing_santander",
    "Racing Santander": "racing_santander",
    # Defaults: _slugify will be used as fallback
}


def scrape_all_teams(client: httpx.Client, team_names: list[str], season: str = "2526") -> list[TeamWikiData]:
    """Scrape all teams, falling back to overview page for missing data."""
    overview = scrape_laliga_overview(client, season)
    results = []

    for name in team_names:
        # Canonical team_id from our mapping or slugify
        team_id = WIKI_TO_TEAM_ID.get(name, _slugify(name))
        wiki_slug = name.replace(" ", "_")
        team_data = scrape_team_page(client, wiki_slug, name)

        if team_data is None:
            # Try to fall back to overview data
            key = name.lower()
            if key in overview:
                ov = overview[key]
                from datetime import datetime
                team_data = TeamWikiData(
                    team_id=team_id,
                    team_name=name,
                    season=season,
                    stadium=ov.get("stadium"),
                    stadium_capacity=ov.get("stadium_capacity"),
                    manager=ov.get("manager"),
                    kit_brand=ov.get("kit_brand"),
                    scraped_at=datetime.utcnow().isoformat(),
                    source_url=LALIGA_URL,
                )
            else:
                from datetime import datetime
                team_data = TeamWikiData(
                    team_id=team_id,
                    team_name=name,
                    season=season,
                    scraped_at=datetime.utcnow().isoformat(),
                    missing_fields=["all"],
                )
        else:
            # Override team_id with our canonical one (in case Wikipedia uses different naming)
            team_data.team_id = team_id

        results.append(team_data)
        time.sleep(0.5)  # Be polite

    return results


def save_cache(data: list[TeamWikiData], path: Path) -> None:
    """Save scraped data to JSON cache."""
    path.parent.mkdir(parents=True, exist_ok=True)
    out = []
    for d in data:
        obj = asdict(d)
        out.append(obj)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2))


def load_cache(path: Path) -> Optional[list[TeamWikiData]]:
    """Load from cache if exists."""
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        return [TeamWikiData(**d) for d in data]
    except Exception:
        return None
