"""Pobla elo_ratings con TODOS los partidos en orden cronológico.

K=32 base, HOME_ADV=80.
Importante: el rating se guarda con fecha = matchday (post-partido).
Para anti-leakage, match_elo usa el último rating con matchday < match.matchday_date
(es decir, el rating justo ANTES del partido, que es el POST-partido del partido anterior).

Si no hay rating con matchday < match.matchday_date, se usa INITIAL_ELO.
"""
import logging
import sqlite3
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "quiniela.db"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)

INITIAL_ELO = 1500.0
K_BASE = 32.0
HOME_ADV = 80.0


def expected_score(rating_a: float, rating_b: float) -> float:
    return 1.0 / (1.0 + 10.0 ** ((rating_b - rating_a) / 400.0))


def actual_score(home_goals: int, away_goals: int) -> tuple:
    if home_goals > away_goals:
        return 1.0, 0.0
    elif home_goals == away_goals:
        return 0.5, 0.5
    return 0.0, 1.0


def main():
    conn = sqlite3.connect(DB)
    log.info("Cargando partidos...")
    df = pd.read_sql_query("""
        SELECT match_id, matchday_date, home_team, away_team,
               home_goals, away_goals, result
        FROM matches
        WHERE result IS NOT NULL AND matchday_date IS NOT NULL
        ORDER BY matchday_date
    """, conn)
    log.info(f"Partidos: {len(df)}")

    ratings: dict[str, float] = {}
    # Guardamos: por equipo, último rating y su fecha
    last_rating_date: dict[str, str] = {}
    history: list[tuple] = []

    for i, m in df.iterrows():
        h = m["home_team"]
        a = m["away_team"]
        d = m["matchday_date"]
        r_h = ratings.get(h, INITIAL_ELO)
        r_a = ratings.get(a, INITIAL_ELO)

        e_h = expected_score(r_h + HOME_ADV, r_a)
        e_a = 1.0 - e_h
        s_h, s_a = actual_score(m["home_goals"], m["away_goals"])

        new_h = r_h + K_BASE * (s_h - e_h)
        new_a = r_a + K_BASE * (s_a - e_a)

        ratings[h] = new_h
        ratings[a] = new_a
        last_rating_date[h] = d
        last_rating_date[a] = d

        # Importante: para evitar que el rating POST del partido N compita con el
        # rating POST del partido N+1 (mismo día), guardamos UNA entrada por
        # (team, matchday). Si ya existe, sobreescribimos.
        history.append((h, d, new_h))
        history.append((a, d, new_a))

        if i % 2000 == 0:
            log.info(f"  {i}/{len(df)} ({100*i/len(df):.1f}%)")

    # Deduplicar manteniendo el último valor por (team, date)
    by_key = {}
    for team, d, elo in history:
        by_key[(team, d)] = elo
    dedup = [(team, d, elo) for (team, d), elo in by_key.items()]

    cur = conn.cursor()
    cur.execute("DELETE FROM elo_ratings")
    cur.executemany("INSERT OR REPLACE INTO elo_ratings (team_id, match_date, elo) VALUES (?,?,?)", dedup)
    conn.commit()
    n = cur.execute("SELECT COUNT(*) FROM elo_ratings").fetchone()[0]
    log.info(f"✅ elo_ratings: {n} filas")

    last_date = df.iloc[-1]["matchday_date"]
    top = cur.execute("""
        SELECT team_id, elo FROM elo_ratings WHERE match_date = ? ORDER BY elo DESC LIMIT 5
    """, (last_date,)).fetchall()
    log.info(f"Top 5 ELO en {last_date}: {[(t, round(e, 0)) for t, e in top]}")

    conn.close()


if __name__ == "__main__":
    main()
