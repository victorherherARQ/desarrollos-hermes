"""Materializa las features h2h (head-to-head) para TODOS los partidos del dataset.

Genera una tabla match_h2h con una fila por partido y N (5 y 10) y columnas:

    match_id INTEGER PRIMARY KEY
    h2h5_played, h2h5_wins_home, h2h5_draws_home, h2h5_losses_home INT
    h2h5_points_home, h2h5_gf_avg_home, h2h5_ga_avg_home, h2h5_gd_avg_home REAL
    h2h5_home_win_rate, h2h5_home_unbeaten_rate REAL
    h2h5_home_dominance INT
    (idem para h2h10_*)

Anti-leakage: usa SIEMPRE partidos con matchday_date < partido objetivo
(vía src/features/h2h.py).

Uso:
    python3 scripts/seed_h2h.py
"""
from __future__ import annotations

import argparse
import logging
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.features.h2h import h2h_features_for_match

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)

DB = ROOT / "data" / "quiniela.db"

W_NS = [5, 10]

H2H_BASE_COLS = [
    "played", "wins_home", "draws_home", "losses_home",
    "points_home", "gf_avg_home", "ga_avg_home", "gd_avg_home",
    "home_win_rate", "home_unbeaten_rate", "home_dominance",
]


def all_h2h_cols() -> list[str]:
    cols: list[str] = []
    for n in W_NS:
        for c in H2H_BASE_COLS:
            cols.append(f"h2h{n}_{c}")
    return cols


def create_table(cur: sqlite3.Cursor) -> None:
    cols_ddl: list[str] = ["match_id INTEGER NOT NULL"]
    for n in W_NS:
        for c in H2H_BASE_COLS:
            if c in ("played", "wins_home", "draws_home", "losses_home", "home_dominance"):
                cols_ddl.append(f"h2h{n}_{c} INTEGER")
            else:
                cols_ddl.append(f"h2h{n}_{c} REAL")
    cols_ddl.append("created_at TEXT DEFAULT (datetime('now'))")
    cols_ddl.append("PRIMARY KEY (match_id)")
    ddl = "CREATE TABLE IF NOT EXISTS match_h2h (\n  " + ",\n  ".join(cols_ddl) + "\n)"
    cur.execute(ddl)


def row_for_n(feats: dict, n: int) -> tuple:
    vals: list = []
    for c in H2H_BASE_COLS:
        vals.append(feats[f"h2h{n}_{c}"])
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

    cols = all_h2h_cols()
    placeholders = ", ".join(["?"] * (len(cols) + 1))
    insert_sql = (
        f"INSERT OR REPLACE INTO match_h2h (match_id, {', '.join(cols)}) "
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
            f5 = h2h_features_for_match(
                conn, home_team=ht, away_team=at, matchday_date=dt, n=5,
            )
            f10 = h2h_features_for_match(
                conn, home_team=ht, away_team=at, matchday_date=dt, n=10,
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

    n = cur.execute("SELECT COUNT(*) FROM match_h2h").fetchone()[0]
    log.info(f"match_h2h tiene {n} filas")

    for n_val in W_NS:
        played_ge1 = cur.execute(
            f"SELECT COUNT(*) FROM match_h2h WHERE h2h{n_val}_played >= 1"
        ).fetchone()[0]
        played_geq_n = cur.execute(
            f"SELECT COUNT(*) FROM match_h2h WHERE h2h{n_val}_played >= ?",
            (n_val,),
        ).fetchone()[0]
        log.info(f"  h2h{n_val}: con ≥1 h2h={played_ge1}/{n} ({100*played_ge1/n:.1f}%), con ≥{n_val}={played_geq_n} ({100*played_geq_n/n:.1f}%)")

    conn.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Seed h2h features")
    p.add_argument("--batch-size", type=int, default=500)
    run(p.parse_args().batch_size)