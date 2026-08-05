"""Mapea partidos StatsBomb a football-data por (home_team_name, away_team_name, match_date).

StatsBomb usa nombres reales: "Barcelona", "Real Madrid"
Football-data usa slugs: "barcelona", "real_madrid"

Mapeo manual con traductor de slug → nombre real, luego matchear.
"""
import logging
import sqlite3
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "quiniela.db"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)

# Map: football-data slug → StatsBomb name
# StatsBomb names son los oficiales del equipo. Algunos tienen sufijos (B, W).
# football-data: lowercase, snake_case
TEAM_MAP = {
    "alaves": "Deportivo Alavés",
    "ath_bilbao": "Athletic Club",
    "atletico_madrid": "Atlético Madrid",
    "barcelona": "Barcelona",
    "betis": "Real Betis",
    "cadiz": "Cádiz",
    "celta": "Celta Vigo",
    "eibar": "Eibar",
    "elche": "Elche",
    "espanyol": "Espanyol",
    "getafe": "Getafe",
    "girona": "Girona",
    "granada": "Granada",
    "las_palmas": "Las Palmas",
    "leganes": "Leganés",
    "levante": "Levante",
    "levante_ud": "Levante UD",
    "mallorca": "Mallorca",
    "osasuna": "Osasuna",
    "rayo_vallecano": "Rayo Vallecano",
    "real_madrid": "Real Madrid",
    "real_sociedad": "Real Sociedad",
    "sevilla": "Sevilla",
    "valencia": "Valencia",
    "valladolid": "Real Valladolid",
    "villarreal": "Villarreal",
    "mallorca": "Mallorca",
    "malaga": "Málaga",
    "recreativo": "Recreativo Huelva",
    "murcia": "Real Murcia",
    "zaragoza": "Real Zaragoza",
    "sporting_gijon": "Sporting Gijón",
    "tenerife": "CD Tenerife",
    "tenerife_alt": "Tenerife",
    "la_coruna": "RC Deportivo La Coruña",
    "almeria": "Almería",
    "numancia": "Numancia",
    "valladolid": "Real Valladolid",
    "osasuna": "Osasuna",
    "huesca": "SD Huesca",
    "huesca_alt": "Huesca",
    "almeria": "Almería",
    "castellon": "Castellón",
    "burgos": "Burgos CF",
    "miranda": "CD Mirandés",
    "ponferradina": "SD Ponferradina",
    "alcorcon": "Alcorcón",
    "cordoba": "Córdoba CF",
    "elche": "Elche",
    "leganes": "Leganés",
    "logrones": "SD Logroñés",
    "toledo": "CD Toledo",
    "extremadura": "Extremadura UD",
    "ferrol": "Racing Ferrol",
    "gijon": "Sporting Gijón",
    "sabadell": "CE Sabadell",
    "sociedad": "Real Sociedad",
    "barca_b": "Barcelona B",
    "ibiza": "UD Ibiza",
    "amorebieta": "SD Amorebieta",
    "eibar_b": "SD Eibar B",
    "real_sociedad_b": "Real Sociedad B",
    "andorra": "FC Andorra",
    "compostela": "Compostela",
    "real_union": "Real Unión",
    "linense": "RB Linense",
    "inter": "CF Intercity",
    "pena": "Pena Deportiva",
    "algeciras": "Algeciras CF",
    "rmadrid_b": "Real Madrid Castilla",
    "rmadrid_youth": "Real Madrid Sub-19",
    "atletico_madrid_b": "Atlético Madrid B",
    "athletic_b": "Athletic Club B",
    "betis_b": "Real Betis B",
    "sevilla_b": "Sevilla Atlético",
    "valencia_b": "Valencia Mestalla",
    "villarreal_b": "Villarreal B",
}


def main():
    conn = sqlite3.connect(DB)

    # Cargar StatsBomb
    sb = pd.read_sql_query("SELECT * FROM statsbomb_xg_matches", conn)
    sb["match_date"] = pd.to_datetime(sb["match_date"])
    log.info(f"StatsBomb: {len(sb)} partidos")

    # Cargar football-data matches
    fd = pd.read_sql_query("""
        SELECT match_id, matchday_date, home_team, away_team, result
        FROM matches WHERE result IS NOT NULL
    """, conn)
    fd["matchday_date"] = pd.to_datetime(fd["matchday_date"])
    log.info(f"Football-data: {len(fd)} partidos")

    # Mapear StatsBomb a football-data slug
    inv_map = {real_name: slug for slug, real_name in TEAM_MAP.items() if real_name}
    sb["home_slug"] = sb["home_team_name"].map(inv_map)
    sb["away_slug"] = sb["away_team_name"].map(inv_map)

    n_unmapped_h = sb["home_slug"].isna().sum()
    n_unmapped_a = sb["away_slug"].isna().sum()
    log.info(f"Unmapped home: {n_unmapped_h}, away: {n_unmapped_a}")
    if n_unmapped_h > 0:
        for n in sb.loc[sb["home_slug"].isna(), "home_team_name"].unique()[:20]:
            log.info(f"  unmapped home: {n!r}")
    if n_unmapped_a > 0:
        for n in sb.loc[sb["away_slug"].isna(), "away_team_name"].unique()[:20]:
            log.info(f"  unmapped away: {n!r}")

    # Match por (home_slug, away_slug, date)
    sb["match_key"] = sb.apply(lambda r: (r["home_slug"], r["away_slug"], r["match_date"]), axis=1)
    fd["match_key"] = fd.apply(lambda r: (r["home_team"], r["away_team"], r["matchday_date"]), axis=1)

    fd_lookup = dict(zip(fd["match_key"], fd["match_id"]))
    sb["fd_match_id"] = sb["match_key"].map(fd_lookup)

    matched = sb["fd_match_id"].notna().sum()
    log.info(f"Matched: {matched}/{len(sb)} ({100*matched/len(sb):.1f}%)")

    # Los unmapped restantes: probar match fuzzy por ±1 día
    if matched < len(sb):
        log.info("Probando match fuzzy ±2 días...")
        fd_by_teams = {}
        for _, row in fd.iterrows():
            key = (row["home_team"], row["away_team"])
            fd_by_teams.setdefault(key, []).append(row)

        unmapped = sb[sb["fd_match_id"].isna()]
        fuzzy_matched = 0
        for idx, row in unmapped.iterrows():
            key = (row["home_slug"], row["away_slug"])
            if key not in fd_by_teams or pd.isna(key[0]) or pd.isna(key[1]):
                continue
            candidates = fd_by_teams[key]
            best = None
            best_diff = None
            for cand in candidates:
                diff = abs((cand["matchday_date"] - row["match_date"]).days)
                if best_diff is None or diff < best_diff:
                    best = cand
                    best_diff = diff
            if best is not None and best_diff <= 2:
                sb.at[idx, "fd_match_id"] = best["match_id"]
                fuzzy_matched += 1
        log.info(f"Fuzzy matched: {fuzzy_matched}")

    matched_total = sb["fd_match_id"].notna().sum()
    log.info(f"Total matched: {matched_total}/{len(sb)} ({100*matched_total/len(sb):.1f}%)")

    # Crear tabla mapeo
    conn.execute("""
        CREATE TABLE IF NOT EXISTS statsbomb_xg_mapped (
            fd_match_id INTEGER PRIMARY KEY,
            home_xg REAL,
            away_xg REAL,
            source TEXT
        )
    """)
    conn.execute("DELETE FROM statsbomb_xg_mapped")
    conn.commit()

    mapped = sb.dropna(subset=["fd_match_id"])[["statsbomb_match_id", "fd_match_id", "home_xg", "away_xg"]].copy()
    mapped["fd_match_id"] = mapped["fd_match_id"].astype(int)
    mapped["statsbomb_match_id"] = mapped["statsbomb_match_id"].astype(int)
    mapped["source"] = "statsbomb"
    mapped.to_sql("statsbomb_xg_mapped", conn, if_exists="append", index=False)

    n = conn.execute("SELECT COUNT(*) FROM statsbomb_xg_mapped").fetchone()[0]
    log.info(f"✅ statsbomb_xg_mapped: {n} partidos")

    # Cobertura por temporada football-data
    log.info("\nCobertura por temporada:")
    rows = conn.execute("""
        SELECT m.season, COUNT(s.fd_match_id) AS con_xg, COUNT(m.match_id) AS total
        FROM matches m
        LEFT JOIN statsbomb_xg_mapped s ON m.match_id = s.fd_match_id
        WHERE m.result IS NOT NULL
        GROUP BY m.season ORDER BY m.season DESC LIMIT 15
    """).fetchall()
    for r in rows:
        if r[1] > 0:
            log.info(f"  {r[0]}: {r[1]}/{r[2]} ({100*r[1]/r[2]:.1f}%) con xG StatsBomb")

    conn.close()


if __name__ == "__main__":
    main()