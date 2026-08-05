"""Genera propuesta de apuesta para una jornada de la Quiniela.

Inputs:
  - quiniela_calendar: jornada + fecha
  - matches de la BD con fecha en el rango de la jornada
  - match_odds: cuotas de mercado (Task 1)

Output:
  - Tabla quiniela_proposals con pronóstico H/D/A para cada partido
  - Para Telegram: convierte H/D/A a 1/X/2

Lógica:
  - Si match_odds disponible: usar ArgMax (AvgH baseline 51.27% en 2526)
  - Si no: usar fallback 'H' (local)
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


def get_jornada(conn: sqlite3.Connection, jornada: int, season: str = "2627") -> tuple[str, str] | None:
    """Devuelve (fecha_sabado, fecha_lunes) para la jornada, o None."""
    r = conn.execute(
        "SELECT fecha_sabado, fecha_lunes FROM quiniela_calendar WHERE jornada=? AND season=?",
        (jornada, season),
    ).fetchone()
    return r if r else None


def get_matches(conn: sqlite3.Connection, fecha_sabado: str, fecha_lunes: str) -> list[dict]:
    """Devuelve partidos de LaLiga en el rango de la jornada."""
    rows = conn.execute(
        """
        SELECT match_id, matchday_date, home_team, away_team, result
        FROM matches
        WHERE matchday_date BETWEEN ? AND ?
              AND result IS NOT NULL
        ORDER BY matchday_date, match_id
        """,
        (fecha_sabado, fecha_lunes),
    ).fetchall()
    return [
        {"match_id": r[0], "date": r[1], "home": r[2], "away": r[3], "result": r[4]}
        for r in rows
    ]


def get_odds(conn: sqlite3.Connection, match_id: int) -> dict | None:
    """Devuelve odds_avg_h/d/a para el partido, o None."""
    r = conn.execute(
        """
        SELECT avg_h, avg_d, avg_a
        FROM match_odds
        WHERE match_id = ?
        """,
        (match_id,),
    ).fetchone()
    if not r or not any(r):
        return None
    return {"avg_h": r[0], "avg_d": r[1], "avg_a": r[2]}


def predict_1x2(avg_h, avg_d, avg_a) -> str:
    """Predice H/D/A a partir de avg_h, avg_d, avg_a (mismo formato que matches.result)."""
    if avg_h is None or avg_d is None or avg_a is None:
        return "H"
    h, d, a = 1.0 / avg_h, 1.0 / avg_d, 1.0 / avg_a
    s = h + d + a
    h, d, a = h / s, d / s, a / s
    if h >= d and h >= a:
        return "H"
    elif d >= a:
        return "D"
    return "A"


_LETTER_TO_DIGIT = {"H": "1", "D": "X", "A": "2"}


def predict_1x2_dict(odds: dict | None) -> str:
    """Devuelve H/D/A."""
    if not odds:
        return "H"
    return predict_1x2(odds.get("avg_h"), odds.get("avg_d"), odds.get("avg_a"))


def to_digit(pred: str) -> str:
    """Convierte H/D/A a 1/X/2 para la quiniela."""
    return _LETTER_TO_DIGIT.get(pred, "1")


def create_proposals_table(cur: sqlite3.Cursor) -> None:
    cur.execute("""
        CREATE TABLE IF NOT EXISTS quiniela_proposals (
            jornada INTEGER NOT NULL,
            season TEXT NOT NULL,
            match_id INTEGER NOT NULL,
            match_date TEXT,
            home_team TEXT,
            away_team TEXT,
            prediction TEXT NOT NULL,
            prediction_digit TEXT,
            odds_avg_h REAL,
            odds_avg_d REAL,
            odds_avg_a REAL,
            prob_h REAL,
            prob_d REAL,
            prob_a REAL,
            generated_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (jornada, season, match_id)
        )
    """)


def generate_proposal(conn: sqlite3.Connection, jornada: int, season: str = "2627") -> dict:
    """Genera propuesta para una jornada. Devuelve dict con resumen."""
    cur = conn.cursor()
    create_proposals_table(cur)

    c = get_jornada(conn, jornada, season)
    if not c:
        return {"error": f"Jornada {jornada} no encontrada en calendario"}
    fecha_sabado, fecha_lunes = c

    matches = get_matches(conn, fecha_sabado, fecha_lunes)
    if not matches:
        return {"error": f"No hay partidos para J{jornada} ({fecha_sabado}-{fecha_lunes})"}

    log.info(f"J{jornada} ({fecha_sabado} ↔ {fecha_lunes}): {len(matches)} partidos")

    # Limpiar propuestas anteriores
    cur.execute(
        "DELETE FROM quiniela_proposals WHERE jornada=? AND season=?",
        (jornada, season),
    )

    lines = []
    for m in matches:
        odds = get_odds(conn, m["match_id"])
        pred = predict_1x2_dict(odds)
        probs = None
        if odds:
            h = 1.0 / odds["avg_h"]
            d = 1.0 / odds["avg_d"]
            a = 1.0 / odds["avg_a"]
            s = h + d + a
            probs = (h / s, d / s, a / s)
        cur.execute(
            """
            INSERT INTO quiniela_proposals
                (jornada, season, match_id, match_date, home_team, away_team,
                 prediction, prediction_digit, odds_avg_h, odds_avg_d, odds_avg_a,
                 prob_h, prob_d, prob_a)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (jornada, season, m["match_id"], m["date"], m["home"], m["away"],
             pred, to_digit(pred),
             odds["avg_h"] if odds else None,
             odds["avg_d"] if odds else None,
             odds["avg_a"] if odds else None,
             probs[0] if probs else None,
             probs[1] if probs else None,
             probs[2] if probs else None),
        )
        lines.append({
            "match_id": m["match_id"],
            "date": m["date"],
            "home": m["home"],
            "away": m["away"],
            "prediction": pred,
            "prediction_digit": to_digit(pred),
            "has_odds": odds is not None,
            "result": m["result"],
        })

    conn.commit()

    # Stats
    n_odds = sum(1 for l in lines if l["has_odds"])
    n_no_odds = len(lines) - n_odds
    n_correct = 0
    n_total = 0
    for l in lines:
        if l["has_odds"]:
            n_total += 1
            if l["prediction"] == l["result"]:
                n_correct += 1

    return {
        "jornada": jornada,
        "season": season,
        "fecha_sabado": fecha_sabado,
        "fecha_lunes": fecha_lunes,
        "n_matches": len(lines),
        "n_with_odds": n_odds,
        "n_without_odds": n_no_odds,
        "n_correct": n_correct,
        "n_total_with_odds": n_total,
        "accuracy": n_correct / n_total if n_total > 0 else None,
        "lines": lines,
    }


def fmt_proposal(proposal: dict) -> str:
    """Formatea propuesta para envío a Telegram."""
    if "error" in proposal:
        return f"❌ {proposal['error']}"

    out = []
    out.append(f"🎯 **PROPUESTA QUINIELA J{proposal['jornada']}**")
    out.append(f"📅 {proposal['fecha_sabado']} → {proposal['fecha_lunes']}")
    out.append(f"⚽ {proposal['n_matches']} partidos ({proposal['n_with_odds']} con cuotas)")
    out.append("")

    emoji = {"H": "🏠", "D": "🤝", "A": "✈️"}
    for i, l in enumerate(proposal["lines"], 1):
        icon = emoji[l["prediction"]]
        odds = "✓odds" if l["has_odds"] else "no-odds"
        result_info = f" (real: {l['result']})" if l["result"] else ""
        out.append(f"  {i:2d}. {icon} **{l['prediction_digit']}** | {l['home']} vs {l['away']} [{odds}]{result_info}")

    if proposal["accuracy"] is not None:
        out.append("")
        out.append(f"📊 Backtest: {proposal['n_correct']}/{proposal['n_total_with_odds']} = {100*proposal['accuracy']:.1f}%")
    return "\n".join(out)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--jornada", type=int, required=True, help="jornada (1-38)")
    p.add_argument("--season", default="2627")
    args = p.parse_args()

    conn = sqlite3.connect(DB)
    proposal = generate_proposal(conn, args.jornada, args.season)
    print(fmt_proposal(proposal))
    conn.close()


if __name__ == "__main__":
    main()
