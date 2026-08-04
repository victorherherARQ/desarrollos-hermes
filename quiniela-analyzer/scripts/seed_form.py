"""Materializa las features de forma para TODOS los partidos del dataset.

Genera una tabla match_form con una fila por partido y N (5 y 10) y columnas:

    match_id INTEGER
    n INT (5 o 10)
    home_points, home_wins, home_draws, home_losses INT
    home_gf_avg, home_ga_avg, home_gd_avg REAL
    home_win_streak, home_unbeaten_streak INT
    home_score REAL
    home_n_played INT
    away_points, away_wins, away_draws, away_losses INT
    away_gf_avg, away_ga_avg, away_gd_avg REAL
    away_win_streak, away_unbeaten_streak INT
    away_score REAL
    away_n_played INT
    points_diff, gd_diff, score_diff, win_streak_diff REAL

Anti-leakage: usa SIEMPRE partidos con matchday_date < partido objetivo
(vía src/features/form.py).

Uso:
    python3 scripts/seed_form.py
"""
from __future__ import annotations

import argparse
import logging
import sqlite3
import time
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.features.form import form_features_for_match

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)

DB = Path(__file__).parent.parent / "data" / "quiniela.db"

W_NS = [5, 10]

FORM_BASE_COLS = [
    "points_home", "wins_home", "draws_home", "losses_home",
    "gf_avg_home", "ga_avg_home", "gd_avg_home",
    "win_streak_home", "unbeaten_streak_home", "score_home", "n_played_home",
    "points_away", "wins_away", "draws_away", "losses_away",
    "gf_avg_away", "ga_avg_away", "gd_avg_away",
    "win_streak_away", "unbeaten_streak_away", "score_away", "n_played_away",
    "points_diff", "gd_diff", "score_diff", "win_streak_diff",
]


def all_form_cols() -> list[str]:
    """Genera la lista completa de columnas para N=5 y N=10."""
    cols: list[str] = []
    for n in W_NS:
        for c in FORM_BASE_COLS:
            cols.append(f"f{n}_{c}")
    return cols


def create_table(cur: sqlite3.Cursor) -> None:
    """Crea la tabla match_form si no existe (idempotente)."""
    cols_ddl: list[str] = ["match_id INTEGER NOT NULL"]
    for n in W_NS:
        for c in FORM_BASE_COLS:
            if "diff" in c or "avg" in c or "score" in c:
                cols_ddl.append(f"f{n}_{c} REAL")
            else:
                cols_ddl.append(f"f{n}_{c} INTEGER")
    cols_ddl.append("created_at TEXT DEFAULT (datetime('now'))")
    cols_ddl.append("PRIMARY KEY (match_id)")
    ddl = "CREATE TABLE IF NOT EXISTS match_form (\n  " + ",\n  ".join(cols_ddl) + "\n)"
    cur.execute(ddl)


def row_for_n(feats: dict, n: int) -> tuple:
    """Extrae (en orden FORM_BASE_COLS) los valores para una N concreta."""
    vals: list = []
    for c in FORM_BASE_COLS:
        vals.append(feats[f"form{n}_{c}"])
    return tuple(vals)


def run(batch_size: int = 500) -> None:
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    create_table(cur)
    conn.commit()

    cur.execute("SELECT COUNT(*) FROM matches")
    total_matches = cur.fetchone()[0]
    log.info(f"Total partidos: {total_matches}")

    cur.execute("SELECT match_id, season, division, matchday_date, home_team, away_team FROM matches")
    rows = cur.fetchall()
    log.info(f"Cargados {len(rows)} partidos")

    form_cols = all_form_cols()
    placeholders = ", ".join(["?"] * (len(form_cols) + 1))  # +1 por match_id
    insert_sql = (
        f"INSERT OR REPLACE INTO match_form (match_id, {', '.join(form_cols)}) "
        f"VALUES ({placeholders})"
    )

    t0 = time.time()
    inserted = 0
    skipped = 0
    batch: list[tuple] = []

    for mid, season, division, dt, ht, at in rows:
        if ht is None or at is None or dt is None:
            skipped += 1
            continue
        try:
            # Combinar features para N=5 y N=10 en una sola pasada de historia
            from src.features.form import form_for_team
            f5 = form_features_for_match(
                conn, season=season, division=division,
                home_team=ht, away_team=at, matchday_date=dt, n=5,
            )
            f10 = form_features_for_match(
                conn, season=season, division=division,
                home_team=ht, away_team=at, matchday_date=dt, n=10,
            )
            vals5 = row_for_n(f5, 5)
            vals10 = row_for_n(f10, 10)
            batch.append((mid,) + vals5 + vals10)
        except Exception as e:
            log.warning(f"match {mid} falló: {e}")
            skipped += 1
            continue

        if len(batch) >= batch_size:
            cur.executemany(insert_sql, batch)
            conn.commit()
            inserted += len(batch)
            batch = []
            elapsed = time.time() - t0
            rate = inserted / elapsed if elapsed > 0 else 0
            eta = (total_matches - inserted) / rate if rate > 0 else 0
            log.info(
                f"  {inserted}/{total_matches} "
                f"({100*inserted/total_matches:.1f}%) "
                f"{rate:.0f} matches/s ETA {eta:.0f}s"
            )

    if batch:
        cur.executemany(insert_sql, batch)
        conn.commit()
        inserted += len(batch)

    elapsed = time.time() - t0
    log.info(f"Total insertados: {inserted}, skipped: {skipped}, elapsed: {elapsed:.1f}s")

    # Verificación rápida
    n = cur.execute("SELECT COUNT(*) FROM match_form").fetchone()[0]
    log.info(f"match_form tiene {n} filas")

    # Cobertura por N
    for n_val in W_NS:
        cov = cur.execute(
            f"SELECT COUNT(*) FROM match_form WHERE f{n_val}_n_played_home >= ?",
            (n_val,),
        ).fetchone()[0]
        log.info(f"  Cobertura form{n_val} con ventana completa: {cov}/{n} ({100*cov/n:.1f}%)")

    conn.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Seed team form features")
    p.add_argument("--batch-size", type=int, default=500)
    run(p.parse_args().batch_size)