"""Generador del calendario 2026-27 de la Quiniela (basado en patrón LaLiga).

Fuentes oficiales:
- Apertura LaLiga 2026-27: 14-17 agosto 2026
- Cierre LaLiga 2026-27: 30 mayo 2027
- 38 jornadas (sábados/domingos, con partidos viernes/lunes)
- Pausa de Navidad (jornadas suspendidas en torno al 24-25 Dic)
- Pausa de Semana Santa (semana de Pascua)
- Partidos entre semana (martes/miércoles) para algunas jornadas

Patrón estándar:
  J1-J4:  agosto-septiembre (sáb/dom cada semana)
  J5-J19: septiembre-diciembre
  J20-J21: NAVIDAD (jornadas suspendidas o single match a finales de dic)
  J22-J38: enero-mayo

Output: tabla `quiniela_calendar` en DB con jornada, fecha_inicio, fecha_fin,
        tipo (regular / navidad / week_double).
"""
from __future__ import annotations

import argparse
import logging
import sqlite3
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "quiniela.db"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)


def generar_calendario_2526() -> list[dict]:
    """Calendario 2025-26: usado solo para backtest (validación retrospectiva)."""
    jornadas = []
    season_start = date(2025, 8, 15)
    current = season_start
    christmas_start = date(2025, 12, 22)
    christmas_end = date(2026, 1, 2)
    easter_start = date(2026, 3, 26)
    easter_end = date(2026, 4, 1)
    j = 1
    while j <= 38:
        if current >= christmas_start and current <= christmas_end:
            current = christmas_end + timedelta(days=1)
        if current >= easter_start and current <= easter_end:
            current = easter_end + timedelta(days=1)
        if current > date(2026, 5, 31):
            break
        while current.weekday() != 5:
            current += timedelta(days=1)
        jornadas.append({
            "jornada": j,
            "season": "2526",
            "fecha_sabado": current.isoformat(),
            "fecha_lunes": (current + timedelta(days=2)).isoformat(),
            "tipo": "opening" if j == 1 else "regular",
        })
        current = current + timedelta(days=7)
        j += 1
    return jornadas


def generar_calendario_2026_27() -> list[dict]:
    """Genera el calendario 2026-27 de la quiniela.

    Aproximación determinista basada en:
      - Apertura: sábado 15 ago 2026 (J1)
      - Cada jornada empieza sábado (fecha principal) y termina lunes
      - Saltamos Navidad (alrededor 24-26 dic) y Semana Santa
    """
    jornadas = []
    season_start = date(2026, 8, 15)  # J1
    current = season_start

    # Periodos de pausa (Navidad)
    # J21 cae alrededor del 20-22 Dic 2026; la J22 suele empezar en enero
    christmas_start = date(2026, 12, 22)
    christmas_end = date(2027, 1, 2)

    # Semana Santa 2027: Domingo Resurrección = 28 marzo 2027
    # Pausa habitual: 25 marzo - 31 marzo (1 semana)
    easter_start = date(2027, 3, 26)
    easter_end = date(2027, 4, 1)

    j = 1
    while j <= 38:
        # ¿Saltar Navidad? Si current entra en periodo, mover a post-navidad
        if current >= christmas_start and current <= christmas_end:
            current = christmas_end + timedelta(days=1)
        # ¿Saltar Semana Santa?
        if current >= easter_start and current <= easter_end:
            current = easter_end + timedelta(days=1)

        if current > date(2027, 5, 30):
            log.warning(f"J{j} cae fuera de temporada (current={current})")
            break

        # Fecha principal de la jornada: sábado
        # Si current es sábado, OK. Si es lunes (por pausa), ajustar al sábado siguiente
        while current.weekday() != 5:  # weekday 5 = Saturday
            current += timedelta(days=1)

        fecha_inicio = current
        fecha_fin = current + timedelta(days=2)  # sábado a lunes

        tipo = "regular"
        # Jornada 1 = opening weekend
        if j == 1:
            tipo = "opening"

        jornadas.append({
            "jornada": j,
            "season": "2627",
            "fecha_sabado": fecha_inicio.isoformat(),
            "fecha_lunes": fecha_fin.isoformat(),
            "tipo": tipo,
        })

        # Avanzar 1 semana (siguiente sábado)
        current = current + timedelta(days=7)
        j += 1

    return jornadas


def create_table(cur: sqlite3.Cursor) -> None:
    cur.execute("""
        CREATE TABLE IF NOT EXISTS quiniela_calendar (
            jornada INTEGER NOT NULL,
            season TEXT NOT NULL,
            fecha_sabado TEXT NOT NULL,
            fecha_lunes TEXT NOT NULL,
            tipo TEXT DEFAULT 'regular',
            proposal_sent INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (jornada, season)
        )
    """)


def upsert(conn: sqlite3.Connection, cur: sqlite3.Cursor, j: dict) -> None:
    cur.execute(
        """
        INSERT OR REPLACE INTO quiniela_calendar
            (jornada, season, fecha_sabado, fecha_lunes, tipo)
        VALUES (:jornada, :season, :fecha_sabado, :fecha_lunes, :tipo)
        """,
        j,
    )


def run() -> None:
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    create_table(cur)
    conn.commit()

    calendar_2627 = generar_calendario_2026_27()
    calendar_2526 = generar_calendario_2526()
    calendar = calendar_2627 + calendar_2526
    log.info(f"Generadas {len(calendar_2627)} jornadas 2627 + {len(calendar_2526)} jornadas 2526 = {len(calendar)}")

    for j in calendar:
        upsert(conn, cur, j)

    conn.commit()

    # Verificación
    n = cur.execute("SELECT COUNT(*) FROM quiniela_calendar").fetchone()[0]
    log.info(f"quiniela_calendar: {n} jornadas cargadas")

    # Mostrar primeras 5 + últimas 3
    print("\n=== Primeras jornadas ===")
    rows = cur.execute(
        "SELECT jornada, fecha_sabado, fecha_lunes, tipo FROM quiniela_calendar ORDER BY jornada LIMIT 5"
    ).fetchall()
    for r in rows:
        print(f"  J{r[0]:2d}  {r[1]} → {r[2]}  ({r[3]})")

    print("\n=== Últimas jornadas ===")
    rows = cur.execute(
        "SELECT jornada, fecha_sabado, fecha_lunes, tipo FROM quiniela_calendar ORDER BY jornada DESC LIMIT 3"
    ).fetchall()
    for r in reversed(rows):
        print(f"  J{r[0]:2d}  {r[1]} → {r[2]}  ({r[3]})")

    # Verificar pausas
    print("\n=== Pausas detectadas ===")
    prev_date = None
    for j, fs in cur.execute("SELECT jornada, fecha_sabado FROM quiniela_calendar ORDER BY jornada").fetchall():
        fs_date = date.fromisoformat(fs)
        if prev_date:
            gap = (fs_date - prev_date).days
            if gap > 9:
                print(f"  J{j}: pausa de {gap} días (de {prev_date} a {fs_date})")
        prev_date = fs_date

    conn.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--season", default="2627", help="temporada, ej 2627")
    args = p.parse_args()
    run()