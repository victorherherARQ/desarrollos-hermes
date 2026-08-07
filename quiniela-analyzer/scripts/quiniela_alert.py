#!/usr/bin/env python3
"""Cron job: monitoriza propuestas de La Quiniela entre semana.

Comportamiento:
  - Cada día (lun-vie) verifica si la quiniela oficial está publicada
  - Si NO está publicada la quiniela → silencio
  - Si está publicada pero NO hay propuesta → avisa (alta)
  - Si hay propuesta pero desactualizada (>24h) → avisa (media)
  - Si está al día → silencio

Uso:
  python3 scripts/quiniela_alert.py
  python3 scripts/quiniela_alert.py --today 2026-08-12 --dry-run
"""
from __future__ import annotations

import argparse
import logging
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "quiniela.db"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)

MAX_AGE_HOURS = 24


def find_lae_quiniela(conn, saturday):
    """¿Está publicada la quiniela oficial en lae_quiniela?"""
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM lae_quiniela WHERE match_date = ?",
        (saturday.isoformat(),),
    )
    r = cur.fetchone()
    return r and r[0] > 0


def next_weekend(today: date) -> tuple[date, date]:
    """Devuelve (sábado, lunes) del finde actual o próximo."""
    weekday = today.weekday()
    if weekday == 5:
        saturday = today
    elif weekday == 6:
        saturday = today - timedelta(days=1)
    else:
        days_to_saturday = 5 - weekday
        saturday = today + timedelta(days=days_to_saturday)
    monday = saturday + timedelta(days=2)
    return saturday, monday


def find_weekend_jornada(conn, today):
    """Devuelve (jornada, season, fecha_sabado, fecha_lunes) del finde actual o próximo."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT jornada, season, fecha_sabado, fecha_lunes, proposal_sent, alert_sent
        FROM quiniela_calendar
        WHERE fecha_lunes >= ?
        ORDER BY fecha_sabado
        LIMIT 1
        """,
        (today.isoformat(),),
    )
    row = cur.fetchone()
    if row:
        return row
    cur.execute(
        """
        SELECT jornada, season, fecha_sabado, fecha_lunes, proposal_sent, alert_sent
        FROM quiniela_calendar
        WHERE fecha_sabado > ?
        ORDER BY fecha_sabado
        LIMIT 1
        """,
        (today.isoformat(),),
    )
    return cur.fetchone()


def proposal_status(conn, jornada, season):
    """Estado de la propuesta."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT COUNT(*) AS total,
               MAX(generated_at) AS last_generated
        FROM quiniela_proposals
        WHERE jornada = ? AND season = ?
        """,
        (jornada, season),
    )
    row = cur.fetchone()
    if not row or row[0] == 0:
        return {"exists": False, "total": 0, "last_generated": None, "age_hours": None}
    total = row[0]
    last_gen = row[1]
    age_hours = None
    if last_gen:
        try:
            last_gen_dt = datetime.fromisoformat(last_gen.replace(" ", "T"))
            age_hours = (datetime.now() - last_gen_dt).total_seconds() / 3600
        except (ValueError, AttributeError):
            pass
    return {
        "exists": True,
        "total": total,
        "last_generated": last_gen,
        "age_hours": age_hours,
        "is_fresh": age_hours is not None and age_hours < MAX_AGE_HOURS,
        "needs_update": age_hours is None or age_hours >= MAX_AGE_HOURS,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--today", default=None, help="YYYY-MM-DD")
    args = p.parse_args()

    today = date.fromisoformat(args.today) if args.today else date.today()
    log.info(f"Hoy: {today} ({today.strftime('%A')})")

    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    match = find_weekend_jornada(conn, today)
    if not match:
        print("📅 No hay jornada programada")
        conn.close()
        return

    jornada, season, fs, fl, proposal_sent, alert_sent = match
    log.info(f"J{jornada} ({season}): sábado {fs} → lunes {fl}")

    saturday = date.fromisoformat(fs)
    days_to_saturday = (saturday - today).days

    lae_published = find_lae_quiniela(conn, saturday)
    log.info(f"LAE quiniela publicada: {lae_published}")

    status = proposal_status(conn, jornada, season)

    # 1. LAE aún no ha publicado la quiniela
    if not lae_published:
        print(f"⏳ J{jornada} ({season}) — LAE aún no ha publicado la quiniela oficial")
        print(f"   Sábado {fs} → Lunes {fl} (en {days_to_saturday} días)")
        print(f"   Cuando LAE la publique, el cron te avisará")
        conn.close()
        return

    # 2. Publicada, sin propuesta
    if not status["exists"]:
        msg_lines = [
            "⚠️ **QUINIELA OFICIAL PUBLICADA**",
            "",
            f"📅 J{jornada} ({season}) empieza en {days_to_saturday} días",
            f"   Sábado {fs} → Lunes {fl}",
            "   ✅ LAE ya publicó los 15 partidos",
            "   ❌ NO hay propuesta generada",
            "",
            f"👉 Pídemela con: 'hazme la propuesta quiniela jornada {jornada}'",
            f"   O ejecuta: `python3 scripts/quiniela_proposal.py --matchday {jornada}`",
        ]
        priority = "alta"
        msg = "\n".join(msg_lines)
    elif status["needs_update"]:
        age_str = f"{status['age_hours']:.1f}h" if status['age_hours'] is not None else "?"
        msg_lines = [
            "⏰ **PROPUESTA QUINIELA DESACTUALIZADA**",
            "",
            f"📅 J{jornada} ({season}) empieza en {days_to_saturday} días",
            f"   Sábado {fs} → Lunes {fl}",
            f"   🕐 Última actualización: {age_str} (>24h)",
            f"   Total partidos: {status['total']}",
            "",
            f"👉 Pide regenerar con: 'regenera la propuesta quiniela J{jornada}'",
        ]
        priority = "media"
        msg = "\n".join(msg_lines)
    else:
        # Al día
        if days_to_saturday <= 0:
            print(f"✅ J{jornada} ({season}) ya jugada o en juego ({fs})")
            print(f"   Propuesta publicada, generada hace {status['age_hours']:.1f}h")
        else:
            print(f"✅ J{jornada} ({season}) — propuesta al día")
            print(f"   Generada hace {status['age_hours']:.1f}h (< {MAX_AGE_HOURS}h)")
            print(f"   Empieza en {days_to_saturday} días (sábado {fs})")
        conn.close()
        return

    print(msg)
    print()
    print(f"   (Prioridad: {priority})")

    if not alert_sent and not args.dry_run:
        cur.execute(
            """
            UPDATE quiniela_calendar
            SET alert_sent = 1, alert_date = ?
            WHERE jornada = ? AND season = ?
            """,
            (today.isoformat(), jornada, season),
        )
        conn.commit()
        log.info(f"J{jornada} marcada como alert_sent=1")

    conn.close()


if __name__ == "__main__":
    main()
