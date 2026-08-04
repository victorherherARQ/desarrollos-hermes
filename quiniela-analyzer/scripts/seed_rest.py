"""Materializa las features de descanso/fatiga para TODOS los partidos.

Tabla `match_rest`:
    match_id INTEGER PRIMARY KEY
    rest_days_home, rest_days_away, rest_days_diff INTEGER
    played_3d_home, played_3d_away, played_4d_home, played_4d_away INT
    played_within_4d_home, played_within_4d_away INT

Anti-leakage: usa siempre el último partido con matchday_date < partido objetivo.

Uso:
    python3 scripts/seed_rest.py
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

from src.features.rest import rest_features_for_match

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)

DB = ROOT / "data" / "quiniela.db"

COLS = [
    "rest_days_home", "rest_days_away", "rest_days_diff",
    "played_3d_home", "played_3d_away", "played_4d_home", "played_4d_away",
    "played_within_4d_home", "played_within_4d_away",
]


def create_table(cur: sqlite3.Cursor) -> None:
    cols_ddl = ["match_id INTEGER NOT NULL"]
    for c in COLS:
        if "played" in c:
            cols_ddl.append(f"{c} INTEGER DEFAULT 0")
        else:
            cols_ddl.append(f"{c} INTEGER")
    cols_ddl.append("created_at TEXT DEFAULT (datetime('now'))")
    cols_ddl.append("PRIMARY KEY (match_id)")
    ddl = "CREATE TABLE IF NOT EXISTS match_rest (\n  " + ",\n  ".join(cols_ddl) + "\n)"
    cur.execute(ddl)


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

    placeholders = ", ".join(["?"] * (len(COLS) + 1))
    insert_sql = (
        f"INSERT OR REPLACE INTO match_rest (match_id, {', '.join(COLS)}) "
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
            feats = rest_features_for_match(
                conn, home_team=ht, away_team=at, matchday_date=dt,
            )
            row_vals = (mid,) + tuple(feats[c] for c in COLS)
            batch.append(row_vals)
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

    n = cur.execute("SELECT COUNT(*) FROM match_rest").fetchone()[0]
    log.info(f"match_rest tiene {n} filas")

    p3 = cur.execute(
        "SELECT COUNT(*) FROM match_rest WHERE played_3d_home=1 OR played_3d_away=1"
    ).fetchone()[0]
    p4 = cur.execute(
        "SELECT COUNT(*) FROM match_rest WHERE played_4d_home=1 OR played_4d_away=1"
    ).fetchone()[0]
    p4d = cur.execute(
        "SELECT COUNT(*) FROM match_rest WHERE played_within_4d_home=1 OR played_within_4d_away=1"
    ).fetchone()[0]
    log.info(f"  equipos con partido 3d antes: {p3} ({100*p3/n:.1f}%)")
    log.info(f"  equipos con partido 4d antes: {p4} ({100*p4/n:.1f}%)")
    log.info(f"  equipos con partido within 4d: {p4d} ({100*p4d/n:.1f}%)")

    avg_rd = cur.execute(
        "SELECT AVG(rest_days_home), AVG(rest_days_away) FROM match_rest WHERE rest_days_home IS NOT NULL"
    ).fetchone()
    log.info(f"  rest_days_home avg: {avg_rd[0]:.2f}, rest_days_away avg: {avg_rd[1]:.2f}")

    conn.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Seed rest features")
    p.add_argument("--batch-size", type=int, default=500)
    run(p.parse_args().batch_size)
