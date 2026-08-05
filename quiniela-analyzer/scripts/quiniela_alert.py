#!/usr/bin/env python3
"""Cron job: detecta jornadas con aviso pendiente (3 días antes) y los manda.

Uso:
  Ejecutar 1 vez al día (ej: 9:00 AM). El script mira la BD y:
    - Encuentra jornadas cuya fecha_sabado está dentro de [3, 5] días
    - Para cada una: genera propuesta + actualiza BD con alert_sent=1
    - Imprime propuesta formateada (el agente Hermes la envía a Telegram)

Cron sugerido:
  0 9 * * * /home/vhdez/desarrollos-hermes/quiniela-analyzer/venv/bin/python3 \\
    /home/vhdez/desarrollos-hermes/quiniela-analyzer/scripts/quiniela_alert.py
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


def add_alert_columns(cur: sqlite3.Cursor) -> None:
    """Asegura que quiniela_calendar tiene columnas alert_sent, alert_date."""
    cur.execute("PRAGMA table_info(quiniela_calendar)")
    cols = {c[1] for c in cur.fetchall()}
    if "alert_sent" not in cols:
        cur.execute("ALTER TABLE quiniela_calendar ADD COLUMN alert_sent INTEGER DEFAULT 0")
    if "alert_date" not in cols:
        cur.execute("ALTER TABLE quiniela_calendar ADD COLUMN alert_date TEXT")


def find_pending_alerts(conn: sqlite3.Connection, today: date = None) -> list[dict]:
    """Encuentra jornadas con aviso pendiente (entre 3 y 5 días vista)."""
    if today is None:
        today = date.today()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT jornada, season, fecha_sabado, fecha_lunes, alert_sent
        FROM quiniela_calendar
        WHERE alert_sent = 0
        """
    )
    out = []
    for j, season, fs, fl, alert_sent in cur.fetchall():
        fs_d = date.fromisoformat(fs)
        avisar = fs_d - timedelta(days=3)
        delta = (avisar - today).days
        if 0 <= delta <= 2:  # avisar hoy o hace 1-2 días (atraso tolerable)
            out.append({
                "jornada": j,
                "season": season,
                "fecha_sabado": fs,
                "fecha_lunes": fl,
                "aviso_date": avisar,
                "delta_days": delta,
            })
    return out


def mark_alert_sent(conn: sqlite3.Connection, jornada: int, season: str, alert_date: date) -> None:
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE quiniela_calendar
        SET alert_sent = 1, alert_date = ?
        WHERE jornada = ? AND season = ?
        """,
        (alert_date.isoformat(), jornada, season),
    )
    conn.commit()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true", help="solo mostrar, no actualizar BD")
    p.add_argument("--today", default=None, help="fecha de hoy (YYYY-MM-DD), default: hoy")
    args = p.parse_args()

    today = date.fromisoformat(args.today) if args.today else date.today()
    log.info(f"Hoy: {today}")

    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    add_alert_columns(cur)
    conn.commit()

    pending = find_pending_alerts(conn, today)
    if not pending:
        print(f"✅ No hay avisos pendientes (próximas 3-5 días)")
        print(f"   Hoy: {today}")
        # Mostrar el siguiente aviso futuro
        cur.execute("""
            SELECT jornada, season, fecha_sabado
            FROM quiniela_calendar
            WHERE alert_sent = 0
            ORDER BY fecha_sabado
            LIMIT 3
        """)
        rows = cur.fetchall()
        for j, s, fs in rows:
            avisar = date.fromisoformat(fs) - timedelta(days=3)
            print(f"   Próximo: J{j} ({s}) → sábado {fs} → avisar {avisar} (en {(avisar-today).days} días)")
        conn.close()
        return

    log.info(f"{len(pending)} aviso(s) pendiente(s)")

    # Import aquí para evitar circular import
    from quiniela_proposal import generate_proposal, fmt_proposal

    for alert in pending:
        log.info(f"Procesando J{alert['jornada']} ({alert['season']})")
        proposal = generate_proposal(conn, alert["jornada"], alert["season"])
        msg = fmt_proposal(proposal)
        print("=" * 60)
        print(msg)
        print("=" * 60)
        if not args.dry_run:
            mark_alert_sent(conn, alert["jornada"], alert["season"], alert["aviso_date"])
            log.info(f"J{alert['jornada']} marcada como alert_sent=1")

    conn.close()


if __name__ == "__main__":
    main()
