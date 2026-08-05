"""Inserta partidos sintéticos de J1 temporada 2627 (LaLiga 2026-27).

Basado en emparejamientos reales de J1 2526 (15-17 ago 2025).
AvgH simulados plausibles para 2026-27 según fuerza relativa de equipos.

Output: partidos insertados en 'matches' con season='2627', result=NULL.
Cuotas simuladas en 'match_odds'.
"""
import logging
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "quiniela.db"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)

# J1 2627 — emparejamientos esperados (basados en J1 2526 + ascensos/descensos LaLiga 2026-27)
# FC: avg_h más bajo (favorito), avg_d ~3.3, avg_a más alto
J1_2627_FIXTURES = [
    # match_id 100000+, jornada 1, season 2627
    # (date, home, away, avg_h, avg_d, avg_a)
    ("2026-08-15", "girona", "vallecano", 2.10, 3.40, 3.60),
    ("2026-08-15", "villarreal", "oviedo", 1.45, 4.30, 7.50),
    ("2026-08-16", "mallorca", "barcelona", 5.50, 4.20, 1.55),
    ("2026-08-16", "alaves", "levante", 2.05, 3.30, 3.80),
    ("2026-08-16", "valencia", "sociedad", 2.65, 3.20, 2.70),
    ("2026-08-17", "celta", "getafe", 2.40, 3.10, 3.10),
    ("2026-08-17", "ath_bilbao", "sevilla", 1.85, 3.50, 4.40),
    ("2026-08-17", "espanol", "ath_madrid", 3.40, 3.30, 2.15),
    ("2026-08-18", "real_madrid", "osasuna", 1.20, 7.00, 15.0),
    ("2026-08-18", "betis", "eibar", 1.65, 3.80, 5.50),
    ("2026-08-18", "rayo_vallecano", "leganes", 1.95, 3.40, 4.00),
    ("2026-08-18", "espanyol", "valladolid", 2.10, 3.30, 3.50),
]


def main():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    # Eliminar partidos sintéticos previos de J1 2627 (idempotente)
    cur.execute("DELETE FROM matches WHERE season = '2627'")
    cur.execute("DELETE FROM match_odds WHERE match_id >= 100000")
    conn.commit()
    log.info("Limpiados partidos sintéticos previos")

    # Insertar fixtures J1 2627
    inserted_matches = 0
    inserted_odds = 0
    match_id_base = 100001
    for i, (date, home, away, ah, ad, aa) in enumerate(J1_2627_FIXTURES):
        mid = match_id_base + i
        try:
            cur.execute("""
                INSERT INTO matches (match_id, season, division, jornada, matchday_date,
                                     home_team, away_team, result, source)
                VALUES (?, '2627', 'SP1', 1, ?, ?, ?, NULL, 'simulated_j1_2627')
            """, (mid, date, home, away))
            inserted_matches += 1
        except Exception as e:
            log.warning(f"Match insert fail: {e}")

        # Pinnacle odds (sharp) y Bet365 (recreacional)
        # avg_* son el promedio de varios bookies
        try:
            cur.execute("""
                INSERT INTO match_odds (
                    match_id, season, division, matchday_date, home_team, away_team,
                    imp_h, imp_d, imp_a, avg_h, avg_d, avg_a,
                    psc_h, psc_d, psc_a, b365c_h, b365c_d, b365c_a, source_url
                )
                VALUES (?, '2627', 'SP1', ?, ?, ?,
                        ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?,
                        'simulated_j1_2627')
            """, (
                mid, date, home, away,
                round(1/ah + 0.01, 4), round(1/ad + 0.01, 4), round(1/aa + 0.01, 4),
                ah, ad, aa,
                round(ah * 0.95, 2), round(ad * 0.98, 2), round(aa * 0.95, 2),  # Pinnacle más bajo
                round(ah * 1.05, 2), round(ad * 1.03, 2), round(aa * 1.05, 2),  # Bet365 closing más alto
            ))
            inserted_odds += 1
        except Exception as e:
            log.warning(f"Odds insert fail: {e}")

    conn.commit()

    n_m = cur.execute("SELECT COUNT(*) FROM matches WHERE season='2627'").fetchone()[0]
    n_o = cur.execute("""SELECT COUNT(*) FROM match_odds o
                          JOIN matches m ON o.match_id = m.match_id
                          WHERE m.season='2627'""").fetchone()[0]
    log.info(f"✅ Insertados: {inserted_matches} matches + {inserted_odds} odds")
    log.info(f"   Total en BD: {n_m} matches J1 2627, {n_o} con odds")

    # Mostrar fixtures
    log.info("\n📋 J1 2627 (LaLiga 2026-27):")
    for r in cur.execute("""
        SELECT m.matchday_date, m.home_team, m.away_team, o.avg_h, o.avg_d, o.avg_a
        FROM matches m
        LEFT JOIN match_odds o ON m.match_id = o.match_id
        WHERE m.season = '2627' AND m.jornada = 1
        ORDER BY m.matchday_date, m.match_id
    """).fetchall():
        print(f"   {r[0]} | {r[1]:16s} vs {r[2]:16s} | AvgH={r[3]:.2f}/{r[4]:.2f}/{r[5]:.2f}")

    conn.close()


if __name__ == "__main__":
    main()