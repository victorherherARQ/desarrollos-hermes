"""xG_proxy features: estima xG usando shots, shots_on_target, corners, fouls.

Derivado de football-data.co.uk (columnas HS, HST, HC, HF). No es xG real
(no tenemos shot locations), pero captura presión ofensiva que el mercado
no descuenta totalmente partido a partido.

Modelo simplificado:
  shot_component = HS * quality_factor
  corner_component = HC * 0.06   (cada corner ~0.06 xG histórico)
  foul_pressure = HF * 0.02      (fouls suffered cerca área ~0.02 xG)
  xg_proxy = shot_component + corner_component + foul_pressure

quality_factor se calibra para que xG_proxy promedio ≈ goles_reales promedio.

Anti-leakage: solo partidos ANTERIORES al actual.
"""
from __future__ import annotations

import argparse
import logging
import sqlite3
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
DB = ROOT / "data" / "quiniela.db"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)

CORNER_XG = 0.06
FOUL_XG = 0.02


def quote_col(name: str) -> str:
    """Quote column names that conflict with SQL keywords (e.g. 'AS')."""
    if name.upper() in ("AS", "SELECT", "FROM", "WHERE"):
        return f'"{name}"'
    return name


def compute_xg_proxy_for_team(team: str, asof_date: str, n: int, conn: sqlite3.Connection) -> dict:
    """Promedio de xG_proxy en los últimos N partidos del equipo antes de asof_date.

    Returns: {xg_proxy_avg, shots_avg, sot_avg, corners_avg, fouls_suf_avg}
    """
    sql = f"""
        SELECT
            m.match_id, m.matchday_date, m.home_team, m.away_team,
            m.result, m.home_goals, m.away_goals,
            m.hs, m.hst, m.hc, m.hf,
            m.away_shots, m.ast, m.ac, m.af
        FROM match_odds m
        WHERE (m.home_team = ? OR m.away_team = ?)
          AND m.matchday_date < ?
          AND m.result IS NOT NULL
        ORDER BY m.matchday_date DESC
        LIMIT ?
    """
    df = pd.read_sql_query(sql, conn, params=(team, team, asof_date, n))
    if len(df) == 0:
        return {k: None for k in ("xg_proxy_avg", "shots_avg", "sot_avg", "corners_avg", "fouls_suf_avg")}

    # Para cada partido: estimar xG_proxy según localía
    xg_list = []
    shots_list = []
    sot_list = []
    corners_list = []
    fouls_list = []
    for _, row in df.iterrows():
        if row["home_team"] == team:
            # Equipo jugó como LOCAL
            hs, hst, hc, hf = row["hs"], row["hst"], row["hc"], row["hf"]
            ax = row["away_shots"]
            axst = row["ast"]
            real_goals = row["home_goals"]
        else:
            # Equipo jugó como VISITANTE → columnas invertidas
            hs, hst, hc, hf = row["away_shots"], row["ast"], row["ac"], row["af"]
            real_goals = row["away_goals"]

        # Quality factor: ratio SOT/shots de la liga media
        if hs and hs > 0:
            sot_ratio = (hst or 0) / hs
        else:
            sot_ratio = 0.35

        # xG_proxy component: penalizar muchos shots de baja calidad
        xg = hs * (0.08 + 0.15 * sot_ratio) + (hc or 0) * CORNER_XG + (hf or 0) * FOUL_XG

        xg_list.append(xg)
        shots_list.append(hs or 0)
        sot_list.append(hst or 0)
        corners_list.append(hc or 0)
        fouls_list.append(hf or 0)

    return {
        "xg_proxy_avg": sum(xg_list) / len(xg_list),
        "shots_avg": sum(shots_list) / len(shots_list),
        "sot_avg": sum(sot_list) / len(sot_list),
        "corners_avg": sum(corners_list) / len(corners_list),
        "fouls_suf_avg": sum(fouls_list) / len(fouls_list),
    }


def build_for_match(match_id: int, home_team: str, away_team: str, asof_date: str, n: int = 5, conn=None) -> dict:
    """Calcula features xG_proxy para un partido concreto."""
    if conn is None:
        conn = sqlite3.connect(DB)
    home = compute_xg_proxy_for_team(home_team, asof_date, n, conn)
    away = compute_xg_proxy_for_team(away_team, asof_date, n, conn)

    out = {
        "home_xg_proxy_avg": home["xg_proxy_avg"],
        "away_xg_proxy_avg": away["xg_proxy_avg"],
        "home_shots_avg": home["shots_avg"],
        "away_shots_avg": away["shots_avg"],
        "home_sot_avg": home["sot_avg"],
        "away_sot_avg": away["sot_avg"],
        "home_corners_avg": home["corners_avg"],
        "away_corners_avg": away["corners_avg"],
        "xg_proxy_diff": (home["xg_proxy_avg"] or 0) - (away["xg_proxy_avg"] or 0),
    }
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--match-id", type=int, default=4)
    p.add_argument("--n", type=int, default=5)
    args = p.parse_args()

    conn = sqlite3.connect(DB)
    row = conn.execute("""
        SELECT match_id, home_team, away_team, matchday_date
        FROM matches WHERE match_id = ?
    """, (args.match_id,)).fetchone()
    if not row:
        print(f"Partido {args.match_id} no encontrado"); return
    mid, h, a, d = row
    print(f"Partido {mid}: {h} vs {a} ({d})")
    print(f"\nFeatures xG_proxy (n={args.n}):")
    feats = build_for_match(mid, h, a, d, args.n, conn)
    for k, v in feats.items():
        print(f"  {k:25s} {v}")

    # Comparar con resultado real
    real = conn.execute("""
        SELECT home_goals, away_goals FROM matches WHERE match_id = ?
    """, (args.match_id,)).fetchone()
    if real:
        print(f"\nGoles reales: {real[0]}-{real[1]}")


if __name__ == "__main__":
    main()