"""Materializa xG_real rolling por equipo.

Usa statsbomb_xg_mapped (xG REAL con shot locations).
Fallback: xG_proxy si no hay StatsBomb.
Anti-leakage: rolling con shift(1) — solo partidos anteriores.
"""
import logging
import sqlite3
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "quiniela.db"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)


def main():
    conn = sqlite3.connect(DB)

    sb_matches = pd.read_sql_query("""
        SELECT fd_match_id AS match_id, home_xg, away_xg
        FROM statsbomb_xg_mapped
    """, conn)
    log.info(f"StatsBomb matches: {len(sb_matches)}")

    matches = pd.read_sql_query("""
        SELECT match_id, matchday_date, home_team, away_team, home_goals, away_goals, result, season
        FROM matches WHERE result IS NOT NULL AND matchday_date IS NOT NULL
        ORDER BY matchday_date
    """, conn)
    matches["matchday_date"] = pd.to_datetime(matches["matchday_date"])
    log.info(f"Football-data matches: {len(matches)}")

    matches = matches.merge(sb_matches, on="match_id", how="left")

    proxy = pd.read_sql_query("""
        SELECT match_id, home_xg_proxy_n5 AS proxy_h5, away_xg_proxy_n5 AS proxy_a5
        FROM match_xg_proxy
    """, conn)
    matches = matches.merge(proxy, on="match_id", how="left")

    # Tabla a nivel equipo-partido: 2 filas por partido (home y away)
    home_rows = pd.DataFrame({
        "match_id": matches["match_id"],
        "matchday_date": matches["matchday_date"],
        "team": matches["home_team"],
        "is_home": True,
        "xg_real": matches["home_xg"],
        "xg_proxy_n5": matches["proxy_h5"],
    })
    away_rows = pd.DataFrame({
        "match_id": matches["match_id"],
        "matchday_date": matches["matchday_date"],
        "team": matches["away_team"],
        "is_home": False,
        "xg_real": matches["away_xg"],
        "xg_proxy_n5": matches["proxy_a5"],
    })
    shots = pd.concat([home_rows, away_rows], ignore_index=True).sort_values("matchday_date")
    log.info(f"Team-match rows: {len(shots)}")

    log.info("Calculando rolling por equipo...")
    out_rows = []
    for team, g in shots.groupby("team"):
        g = g.sort_values("matchday_date").reset_index(drop=True)
        # Anti-leakage: shift(1) excluye el partido actual
        g["team_xg_real_n5"] = g["xg_real"].shift(1).rolling(5, min_periods=3).mean()
        g["team_xg_real_n10"] = g["xg_real"].shift(1).rolling(10, min_periods=5).mean()
        # Fallback a proxy si xG_real es NaN (cuando no hay StatsBomb)
        proxy_n5 = g["xg_proxy_n5"].shift(1).rolling(5, min_periods=3).mean()
        proxy_n10 = g["xg_proxy_n5"].shift(1).rolling(10, min_periods=5).mean()
        g["team_xg_real_n5"] = g["team_xg_real_n5"].fillna(proxy_n5)
        g["team_xg_real_n10"] = g["team_xg_real_n10"].fillna(proxy_n10)
        out_rows.append(g)

    shots = pd.concat(out_rows, ignore_index=True)
    n_filled_n5 = shots["team_xg_real_n5"].notna().sum()
    log.info(f"Rolling calculado. n5 no-null: {n_filled_n5}/{len(shots)} ({100*n_filled_n5/len(shots):.1f}%)")

    # Volver a formato partido
    home_features = shots[shots["is_home"]][["match_id", "team_xg_real_n5", "team_xg_real_n10"]].rename(
        columns={"team_xg_real_n5": "home_xg_real_n5", "team_xg_real_n10": "home_xg_real_n10"})
    away_features = shots[~shots["is_home"]][["match_id", "team_xg_real_n5", "team_xg_real_n10"]].rename(
        columns={"team_xg_real_n5": "away_xg_real_n5", "team_xg_real_n10": "away_xg_real_n10"})

    final = matches.merge(home_features, on="match_id", how="left").merge(away_features, on="match_id", how="left")
    final["xg_real_diff_n5"] = final["home_xg_real_n5"] - final["away_xg_real_n5"]
    final["xg_real_diff_n10"] = final["home_xg_real_n10"] - final["away_xg_real_n10"]

    conn.execute("""
        CREATE TABLE IF NOT EXISTS match_xg_real (
            match_id INTEGER PRIMARY KEY,
            home_xg_real_n5 REAL,
            away_xg_real_n5 REAL,
            xg_real_diff_n5 REAL,
            home_xg_real_n10 REAL,
            away_xg_real_n10 REAL,
            xg_real_diff_n10 REAL,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("DELETE FROM match_xg_real")
    conn.commit()

    out = final[["match_id", "home_xg_real_n5", "away_xg_real_n5", "xg_real_diff_n5",
                 "home_xg_real_n10", "away_xg_real_n10", "xg_real_diff_n10"]]
    out.to_sql("match_xg_real", conn, if_exists="append", index=False)

    n = conn.execute("SELECT COUNT(*) FROM match_xg_real").fetchone()[0]
    n_filled = conn.execute("SELECT COUNT(*) FROM match_xg_real WHERE home_xg_real_n5 IS NOT NULL").fetchone()[0]
    log.info(f"✅ match_xg_real: {n} filas, {n_filled} con home_xg_real_n5 non-null ({100*n_filled/n:.1f}%)")

    log.info("\nCobertura por temporada:")
    rows = conn.execute("""
        SELECT m.season, COUNT(x.match_id) AS con_xg, COUNT(m.match_id) AS total
        FROM matches m
        LEFT JOIN match_xg_real x ON m.match_id = x.match_id
        WHERE m.result IS NOT NULL AND x.home_xg_real_n5 IS NOT NULL
        GROUP BY m.season ORDER BY m.season DESC LIMIT 20
    """).fetchall()
    for r in rows:
        if r[1] > 0:
            log.info(f"  {r[0]}: {r[1]}/{r[2]} ({100*r[1]/r[2]:.1f}%)")

    conn.close()


if __name__ == "__main__":
    main()