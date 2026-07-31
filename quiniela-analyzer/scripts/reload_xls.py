"""Reload all sorteos from XLS into SQLite (truncate + insert)."""
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.scraper.parse_xls import parse_xls

DB = Path("data/quiniela.db")
PLENO_RE = re.compile(r"^[0-2][0-2]?$|^[0-2]M$|^M[0-2]$|^MM$")


def main():
    rows = parse_xls("data/raw/HistoricoQuiniela.xls")
    print(f"Total sorteos parseados: {len(rows)}")

    conn = sqlite3.connect(str(DB))
    c = conn.cursor()
    c.execute("DELETE FROM quiniela_resultados")
    conn.commit()

    counter = defaultdict(int)
    inserted = 0
    for r in rows:
        signs = r["signs"]
        if len(signs) != 15:
            continue
        if r["jornada"] <= 0:
            counter[r["season"]] += 1
            r["jornada"] = counter[r["season"]]
        else:
            if counter[r["season"]] < r["jornada"]:
                counter[r["season"]] = r["jornada"]
        try:
            c.execute(
                """
                INSERT OR REPLACE INTO quiniela_resultados
                (season, season_start, jornada, fecha_sorteo, dia, semana, sorteo,
                 s1,s2,s3,s4,s5,s6,s7,s8,s9,s10,s11,s12,s13,s14,s15, pleno, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?,?,?,?,?,?,?,?,?,?,?,?,?,?, ?, ?, 'xls_selae')
            """,
                (
                    r["season"], r["season_start"], r["jornada"],
                    "", r["dia"], r["semana"], r["sorteo"],
                    signs[0], signs[1], signs[2], signs[3], signs[4],
                    signs[5], signs[6], signs[7], signs[8], signs[9],
                    signs[10], signs[11], signs[12], signs[13], signs[14],
                    r["pleno"] or "",
                ),
            )
            inserted += 1
        except sqlite3.IntegrityError:
            pass
    conn.commit()
    print(f"Insertados: {inserted}")

    # Solo extraer plenos mezclados en s15 cuando NO hay pleno previo (legacy).
    # En legacy (sorteo = fecha), pleno está vacío. En moderna, ya viene en 'pleno'.
    PLENO_PROMOTE_RE = re.compile(r"^(?:[0-2]M|M[0-2]|MM|[0-2][0-2]|[0-2]-(?:M|[0-2]))$")
    updated = 0
    for sid, s15, pleno in c.execute(
        "SELECT id, s15, pleno FROM quiniela_resultados WHERE s15 IS NOT NULL"
    ).fetchall():
        if not pleno and PLENO_PROMOTE_RE.match(s15) and len(s15) <= 3:
            c.execute(
                "UPDATE quiniela_resultados SET pleno=?, s15=NULL WHERE id=?",
                (s15, sid),
            )
            updated += 1
    conn.commit()
    print(f"Plenos extraídos de s15 (legacy): {updated}")

    print("\nDistribución:")
    for row in c.execute(
        """
        SELECT season, COUNT(*) as n, MIN(jornada), MAX(jornada)
        FROM quiniela_resultados
        GROUP BY season
        ORDER BY season_start DESC
    """
    ):
        print(f"  {row[0]}: {row[1]} jornadas (J{row[2]}-J{row[3]})")
    conn.close()


if __name__ == "__main__":
    main()
