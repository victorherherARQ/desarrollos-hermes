"""Materializa xG_proxy rolling para TODOS los partidos.

Versión optimizada: en lugar de iterar partido a partido con rolling
manual, precalcula los stats POR EQUIPO y los une por match_id.
"""
import logging
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "quiniela.db"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)

CORNER_XG = 0.06
FOUL_XG = 0.02


def xg_proxy_row(hs: float, hst: float, hc: float, hf: float) -> float:
    if hs is None or pd.isna(hs) or hs == 0:
        return 0.0
    sot_ratio = (hst or 0) / hs
    return hs * (0.08 + 0.15 * sot_ratio) + (hc or 0) * CORNER_XG + (hf or 0) * FOUL_XG


def add_long_format(df: pd.DataFrame) -> pd.DataFrame:
    """Transforma a formato long: cada fila = (equipo, partido) con su xg_proxy."""
    home = pd.DataFrame({
        "match_id": df["match_id"],
        "matchday_date": df["matchday_date"],
        "team": df["home_team"],
        "xg_for": df.apply(lambda r: xg_proxy_row(r["hs"], r["hst"], r["hc"], r["hf"]), axis=1),
    })
    away = pd.DataFrame({
        "match_id": df["match_id"],
        "matchday_date": df["matchday_date"],
        "team": df["away_team"],
        "xg_for": df.apply(lambda r: xg_proxy_row(r["away_shots"], r["ast"], r["ac"], r["af"]), axis=1),
    })
    return pd.concat([home, away], ignore_index=True).sort_values(["team", "matchday_date"]).reset_index(drop=True)


def rolling_mean_by_team(long_df: pd.DataFrame, n: int, col_prefix: str) -> pd.DataFrame:
    """Para cada (team, match_id): promedio de xg_proxy en los N partidos ANTERIORES.

    Anti-leakage garantizado: rolling con min_periods=1, shift(1) evita incluirse.
    """
    long_df = long_df.sort_values(["team", "matchday_date"]).reset_index(drop=True)
    long_df[f"{col_prefix}_prev"] = long_df.groupby("team")["xg_for"].shift(1)
    long_df[f"{col_prefix}_avgN"] = (
        long_df.groupby("team")[f"{col_prefix}_prev"]
        .transform(lambda s: s.rolling(window=n, min_periods=1).mean())
    )
    return long_df[["team", "match_id", f"{col_prefix}_avgN"]]


def main():
    log.info("Cargando matches...")
    conn = sqlite3.connect(DB)
    df = pd.read_sql_query("""
        SELECT match_id, matchday_date, home_team, away_team, result,
               hs, away_shots, hst, ast, hc, ac, hf, af
        FROM match_odds
        WHERE result IS NOT NULL AND matchday_date IS NOT NULL
        ORDER BY matchday_date
    """, conn)
    log.info(f"Cargados {len(df)} partidos con stats")

    long = add_long_format(df)
    log.info(f"Long format: {len(long)} filas (equipo × partido)")

    # Rolling n=5 y n=10
    r5 = rolling_mean_by_team(long, 5, "xg5")
    r10 = rolling_mean_by_team(long, 10, "xg10")

    # Construir tabla final: para cada match_id, home_xg5 = r5.home_xg5_avg, away_xg5 = r5.away_xg5_avg
    home5 = r5.rename(columns={"team": "home_team", "xg5_avgN": "home_xg_proxy_n5"})[
        ["match_id", "home_team", "home_xg_proxy_n5"]].drop_duplicates(["match_id", "home_team"])
    away5 = r5.rename(columns={"team": "away_team", "xg5_avgN": "away_xg_proxy_n5"})[
        ["match_id", "away_team", "away_xg_proxy_n5"]].drop_duplicates(["match_id", "away_team"])
    home10 = r10.rename(columns={"team": "home_team", "xg10_avgN": "home_xg_proxy_n10"})[
        ["match_id", "home_team", "home_xg_proxy_n10"]].drop_duplicates(["match_id", "home_team"])
    away10 = r10.rename(columns={"team": "away_team", "xg10_avgN": "away_xg_proxy_n10"})[
        ["match_id", "away_team", "away_xg_proxy_n10"]].drop_duplicates(["match_id", "away_team"])

    base = df[["match_id", "home_team", "away_team"]].copy()
    base = base.merge(home5, on=["match_id", "home_team"], how="left")
    base = base.merge(away5, on=["match_id", "away_team"], how="left")
    base = base.merge(home10, on=["match_id", "home_team"], how="left")
    base = base.merge(away10, on=["match_id", "away_team"], how="left")
    base["xg_proxy_diff_n5"] = base["home_xg_proxy_n5"] - base["away_xg_proxy_n5"]
    base["xg_proxy_diff_n10"] = base["home_xg_proxy_n10"] - base["away_xg_proxy_n10"]

    conn.execute("""
        CREATE TABLE IF NOT EXISTS match_xg_proxy (
            match_id INTEGER PRIMARY KEY,
            home_xg_proxy_n5 REAL, away_xg_proxy_n5 REAL, xg_proxy_diff_n5 REAL,
            home_xg_proxy_n10 REAL, away_xg_proxy_n10 REAL, xg_proxy_diff_n10 REAL,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("DELETE FROM match_xg_proxy")
    conn.commit()

    out = base[["match_id", "home_xg_proxy_n5", "away_xg_proxy_n5", "xg_proxy_diff_n5",
                "home_xg_proxy_n10", "away_xg_proxy_n10", "xg_proxy_diff_n10"]]
    out.to_sql("match_xg_proxy", conn, if_exists="append", index=False)

    cur = conn.cursor()
    n_filled = cur.execute("SELECT COUNT(*) FROM match_xg_proxy WHERE home_xg_proxy_n5 IS NOT NULL").fetchone()[0]
    log.info(f"✅ Tabla match_xg_proxy: {len(out)} filas, {n_filled} con n5 non-null")
    stats = cur.execute("""SELECT AVG(home_xg_proxy_n5), AVG(away_xg_proxy_n5),
        AVG(xg_proxy_diff_n5) FROM match_xg_proxy WHERE home_xg_proxy_n5 IS NOT NULL""").fetchone()
    log.info(f"  avg home: {stats[0]:.3f}, avg away: {stats[1]:.3f}, avg diff: {stats[2]:+.3f}")
    conn.close()


if __name__ == "__main__":
    main()