#!/usr/bin/env python3
"""Cron job: monitoriza propuestas de La Quiniela entre semana.

Comportamiento:
  - Cada día (lun-vie) verifica si hay jornada con finde próximo
  - Si la propuesta NO está publicada o el AvgH está desactualizado (>24h),
    avisa a Víctor para que la pida/regeneres
  - Si está al día: silencio (no envía nada)

Casos:
  - finde = sábado+domingo+lunes (15-ago a 17-ago)
  - ventana aviso = lunes 12-ago (3 días antes) hasta viernes 14-ago
  - después de las 18:00 del viernes: silencio (ya no hay tiempo)

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

MAX_AGE_HOURS = 24  # propuesta de más de 24h se considera desactualizada


def next_weekend(today: date) -> tuple[date, date]:
    """Devuelve (sábado, lunes) del próximo fin de semana.

    - Lunes a viernes → próximo sábado
    - Sábado o domingo → mismo finde (sábado actual)
    - Lunes post-finde → próximo sábado
    """
    # lunes=0, ..., sábado=5, domingo=6
    weekday = today.weekday()
    if weekday == 5:  # sábado
        saturday = today
    elif weekday == 6:  # domingo
        saturday = today - timedelta(days=1)
    else:
        # lunes(0), martes(1), miércoles(2), jueves(3), viernes(4)
        days_to_saturday = 5 - weekday
        saturday = today + timedelta(days=days_to_saturday)
    monday = saturday + timedelta(days=2)
    return saturday, monday


def find_weekend_jornada(conn: sqlite3.Connection, today: date):
    """Encuentra la jornada del finde en curso o del próximo.

    - Si hoy cae en [sábado, lunes] del finde → jornada actual
    - Si hoy es martes o posterior → jornada del próximo finde
    """
    cur = conn.cursor()
    # 1) Buscar jornada donde fecha_lunes >= hoy (aún no cerrada)
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

    # 2) Si no hay, buscar la primera jornada futura
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


def proposal_status(conn: sqlite3.Connection, jornada: int, season: str) -> dict:
    """Devuelve el estado de la propuesta: cuántas tiene, cuántas obsoletas, etc."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT COUNT(*) AS total,
               SUM(CASE WHEN generated_at IS NULL THEN 1 ELSE 0 END) AS null_date,
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
    last_gen = row[2]
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
    p.add_argument("--dry-run", action="store_true", help="solo mostrar, no actualizar BD")
    p.add_argument("--today", default=None, help="fecha de hoy (YYYY-MM-DD), default: hoy")
    args = p.parse_args()

    today = date.fromisoformat(args.today) if args.today else date.today()
    log.info(f"Hoy: {today} ({today.strftime('%A')})")

    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    # Buscar próximo finde
    match = find_weekend_jornada(conn, today)
    if not match:
        print(f"📅 No hay jornada programada en las próximas semanas")
        print(f"   Hoy: {today}")
        conn.close()
        return

    jornada, season, fs, fl, proposal_sent, alert_sent = match
    log.info(f"Encontrada J{jornada} ({season}): sábado {fs} → lunes {fl}")

    status = proposal_status(conn, jornada, season)
    saturday = date.fromisoformat(fs)
    days_to_saturday = (saturday - today).days

    # Lógica principal:
    # 1. Si no hay propuesta → avisar (alta prioridad)
    # 2. Si hay propuesta pero es vieja (>24h) → avisar (recordatorio)
    # 3. Si está al día → silencio (no enviar)

    msg_lines = []

    if not status["exists"]:
        msg_lines.append(f"⚠️ **PROPUESTA QUINIELA PENDIENTE**")
        msg_lines.append(f"")
        msg_lines.append(f"📅 J{jornada} ({season}) empieza en {days_to_saturday} días")
        msg_lines.append(f"   Sábado {fs} → Lunes {fl}")
        msg_lines.append(f"")
        msg_lines.append(f"❌ NO hay propuesta generada todavía")
        msg_lines.append(f"")
        msg_lines.append(f"👉 Pídemela con: 'hazme la propuesta quiniela jornada {jornada}'")
        msg_lines.append(f"   O ejecuta: `python3 scripts/quiniela_proposal.py --matchday {jornada}`")
        priority = "alta"
    elif status["needs_update"]:
        msg_lines.append(f"⏰ **PROPUESTA QUINIELA DESACTUALIZADA**")
        msg_lines.append(f"")
        msg_lines.append(f"📅 J{jornada} ({season}) empieza en {days_to_saturday} días")
        msg_lines.append(f"   Sábado {fs} → Lunes {fl}")
        msg_lines.append(f"")
        age_str = f"{status['age_hours']:.1f}h" if status['age_hours'] is not None else "?"
        msg_lines.append(f"🕐 Última actualización: {age_str} (>24h)")
        msg_lines.append(f"   Total partidos: {status['total']}")
        msg_lines.append(f"   AvgH puede haber cambiado desde entonces")
        msg_lines.append(f"")
        msg_lines.append(f"👉 Pide regenerar con: 'regenera la propuesta quiniela J{jornada}'")
        priority = "media"
    else:
        # Propuesta está al día
        if days_to_saturday <= 0:
            # Ya pasó el finde o estamos en él
            print(f"✅ J{jornada} ({season}) ya jugada o en juego ({fs})")
            print(f"   Propuesta publicada, generada hace {status['age_hours']:.1f}h")
        else:
            print(f"✅ J{jornada} ({season}) — propuesta al día")
            print(f"   Generada hace {status['age_hours']:.1f}h (< {MAX_AGE_HOURS}h)")
            print(f"   Empieza en {days_to_saturday} días (sábado {fs})")
        conn.close()
        return

    # Mostrar el aviso
    print("\n".join(msg_lines))
    print()
    print(f"   (Prioridad: {priority})")

    # Marcar como alert_sent solo si no estaba ya marcado
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
