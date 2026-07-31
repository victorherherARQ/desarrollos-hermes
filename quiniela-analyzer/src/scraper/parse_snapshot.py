"""Parse the Camofox accessibility snapshot of loteriasyapuestas.es /es/quiniela/resultados.

The snapshot is JSON with key 'snapshot' containing escaped YAML-ish text.
We decode it and extract jornada/match data.
"""
from __future__ import annotations

import codecs
import json
import re
import sqlite3
from pathlib import Path

# Cada fila tiene formato: row "N. Home - Away score_home - score_away sign"
# Donde sign es 1, X o 2.
# Problema: los nombres de equipos pueden tener guiones intermedios (Sevilla, Real Madrid).
# La regex come desde el número + equipos hasta encontrar "<n> - <m> <signo>" donde signo ∈ {1,X,2}.
ROW_RE = re.compile(
    r'row "(?P<n>\d+)\. (?P<home>[^"]+?) (?P<sh>\d+) - (?P<sa>\d+) (?P<sign>[1X2])":'
)
PLENO_RE = re.compile(
    r'row "P-15 (?P<home>[^"]+?) (?P<sh>\d+) - (?P<sa>\d+) (?P<sign>[\dM]+(?:-[\dM])?)":'
)
JORNADA_RE = re.compile(r'Jornada\s+(\d+)\S*\s+(\w+)\s+-\s+(\d+/\d+/\d+)')


def parse_snapshot(path: Path | str) -> list[dict]:
    """Parse the snapshot JSON file into jornada dicts."""
    path = Path(path)
    raw = json.loads(path.read_text())
    snap = codecs.decode(raw.get("snapshot", ""), "unicode_escape")

    # Split into blocks per jornada
    jornadas_iter = list(JORNADA_RE.finditer(snap))
    results = []
    for i, m in enumerate(jornadas_iter):
        jornada = int(m.group(1))
        day = m.group(2)
        date = m.group(3)
        # Block from this jornada to next (or end of document)
        start = m.end()
        end = jornadas_iter[i + 1].start() if i + 1 < len(jornadas_iter) else len(snap)
        block = snap[start:end]
        # Extraer filas de partido y pleno
        partidos = []
        for fm in ROW_RE.finditer(block):
            partidos.append({
                "n": int(fm.group("n")),
                "home": fm.group("home").strip(),
                "away_etc": "",  # placeholder, hay que separar con regex mejor
                "ghome": int(fm.group("sh")),
                "gaway": int(fm.group("sa")),
                "sign": fm.group("sign"),
            })
        # Mejor: extraer home y away - el "home" actual contiene "Hacken - Aik" porque
        # el equipo es siempre el que va antes y el away después. Necesito separar.
        partidos_v2 = []
        for fm in ROW_RE.finditer(block):
            full = fm.group(0)  # raw
            # Tomar el pedazo entre row "<n>. " y " <gh> - <ga> <sign>"
            inner = full.split('"')[1]  # '1. Villarreal - Levante 5 - 1 1'
            n_part, _, rest = inner.partition(". ")
            # Buscar score y sign al final
            score_match = re.search(r"(\d+) - (\d+) ([1X2])$", rest)
            if not score_match:
                continue
            ghome = int(score_match.group(1))
            gaway = int(score_match.group(2))
            sign = score_match.group(3)
            teams = rest[:score_match.start()].strip()
            # Separar home - away por el último " - "
            if " - " in teams:
                home, away = teams.rsplit(" - ", 1)
            else:
                home, away = teams, ""
            partidos_v2.append({
                "n": int(n_part),
                "home": home.strip(),
                "away": away.strip(),
                "ghome": ghome,
                "gaway": gaway,
                "sign": sign,
            })
        # Pleno
        pleno = None
        for pm in PLENO_RE.finditer(block):
            inner = pm.group(0).split('"')[1]  # 'P-15 Hacken - Aik 0 - 0 0-0'
            _, _, rest = inner.partition(" ")
            score_match = re.search(r"(\d+) - (\d+) ([\dM-]+)$", rest)
            if not score_match:
                continue
            teams = rest[:score_match.start()].strip()
            if " - " in teams:
                home, away = teams.rsplit(" - ", 1)
            else:
                home, away = teams, ""
            pleno = {
                "home": home.strip(),
                "away": away.strip(),
                "ghome": int(score_match.group(1)),
                "gaway": int(score_match.group(2)),
                "sign": score_match.group(3),
            }
            break

        if len(partidos_v2) >= 14:  # sólo guardamos jornadas con la mayoría de partidos
            results.append({
                "jornada": jornada,
                "day": day,
                "date": date,
                "partidos": partidos_v2[:15],
                "pleno": pleno,
            })
    return results


def upsert_to_sqlite(db_path: Path | str, data: list[dict], season: str = "2526", season_start: int = 2025) -> tuple[int, int, int]:
    """Persist scraped data to SQLite. Returns (inserted_jornadas, inserted_partidos, skipped)."""
    conn = sqlite3.connect(str(db_path))
    c = conn.cursor()
    # El schema quiniela_jornadas/quiniela_partidos ya existe del bootstrap inicial.
    # Si necesitas columnas extra (pleno_*), añade migración aquí.
    jor_cols = {r[1] for r in c.execute("PRAGMA table_info(quiniela_jornadas)").fetchall()}
    for col, sql in [("pleno_g_home", "INTEGER"), ("pleno_g_away", "INTEGER"), ("pleno_sign", "TEXT"), ("fecha", "DATE"), ("source", "TEXT DEFAULT 'loteriasyapuestas.es'")]:
        if col not in jor_cols:
            try:
                c.execute(f"ALTER TABLE quiniela_jornadas ADD COLUMN {col} {sql}")
            except sqlite3.IntegrityError:
                pass
    # Migrar columnas de quiniela_resultados si no existen (lo creamos al vuelo)
    # Mapa de columnas para jornada (compatibilidad)
    jor_columns = {r[1] for r in c.execute("PRAGMA table_info(quiniela_jornadas)").fetchall()}

    inserted_j = inserted_p = skipped = 0
    for j in data:
        try:
            # Upsert jornada: usar INSERT OR REPLACE en (season, numero)
            c.execute("SELECT 1 FROM quiniela_jornadas WHERE season=? AND numero=?", (season, j["jornada"]))
            exists = c.fetchone()
            if exists:
                c.execute("""
                UPDATE quiniela_jornadas SET fecha=?, pleno_g_home=?, pleno_g_away=?, pleno_sign=?
                WHERE season=? AND numero=?
                """, (j["date"], j["pleno"]["ghome"] if j["pleno"] else None,
                      j["pleno"]["gaway"] if j["pleno"] else None,
                      j["pleno"]["sign"] if j["pleno"] else None,
                      season, j["jornada"]))
            else:
                c.execute("""
                INSERT INTO quiniela_jornadas (season, numero, fecha, pleno_g_home, pleno_g_away, pleno_sign, source)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (season, j["jornada"], j["date"],
                      j["pleno"]["ghome"] if j["pleno"] else None,
                      j["pleno"]["gaway"] if j["pleno"] else None,
                      j["pleno"]["sign"] if j["pleno"] else None,
                      "loteriasyapuestas.es"))
            row = c.execute("SELECT jornada_id FROM quiniela_jornadas WHERE season=? AND numero=?",
                            (season, j["jornada"])).fetchone()
            if not row:
                skipped += 1
                continue
            jid = row[0]
            for p in j["partidos"]:
                c.execute("""
                INSERT OR REPLACE INTO quiniela_partidos
                (jornada_id, orden, home_team, away_team, home_goals, away_goals, sign, pleno)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (jid, p["n"], p["home"], p["away"], p["ghome"], p["gaway"], p["sign"],
                      j["pleno"]["sign"] if j["pleno"] else None))
                inserted_p += 1
            inserted_j += 1
        except sqlite3.IntegrityError:
            skipped += 1
    conn.commit()
    conn.close()
    return inserted_j, inserted_p, skipped


def main() -> None:
    data = parse_snapshot("/tmp/raw_snap.json")
    print(f"Jornadas parseadas: {len(data)}")
    if data:
        print(f"  Mín: {min(d['jornada'] for d in data)}")
        print(f"  Máx: {max(d['jornada'] for d in data)}")
        d = data[0]
        print(f"\n=== Jornada {d['jornada']} ({d['day']} {d['date']}) — {len(d['partidos'])} partidos ===")
        for p in d["partidos"][:5]:
            print(f"  {p['n']:>2}. {p['home']:>25} {p['ghome']}-{p['gaway']} {p['away']:<25} -> {p['sign']}")
        print(f"  Pleno: {d['pleno']}")
    ins_j, ins_p, skp = upsert_to_sqlite("data/quiniela.db", data)
    print(f"\nUpsert: {ins_j} jornadas, {ins_p} partidos / Skipped: {skp}")


if __name__ == "__main__":
    main()
