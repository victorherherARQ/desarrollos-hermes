"""Parse the SELAE HistoricoQuiniela.xls into a flat list of (season, jornada, signs[]).

The XLS workbook has 1 sheet per season from 1972-73 to 2025-26 (54 sheets).
Sheets have different layouts depending on season:

LAYOUT A (legacy 1988-89 to 2013-14): 35 cols
  col 0: empty
  col 1: jornada number
  col 2: fecha (excel serial) / sorteo
  col 3-17: 15 sign values (1/X/2)
  col 18+: premios (skip)

LAYOUT B (modern 2014-15 to 2018-19): 51 cols
  col 0: empty
  col 1: jornada number
  col 2: sorteo ID
  col 3: dia-info
  col 4: fecha (excel serial)
  col 5-19: 15 sign values (1/X/2)
  col 20: pleno (1/X/2/M-0/M-1/M-2/M-M or score)
  col 21+: premios (skip)

LAYOUT C (modern 2019-20 to 2020-21): 4 cols (BUG: missing sign 15)
  col 0: "X Semana YYYY"
  col 1: Q-DOMINGO / Q-LUNES / Q-JUEVES
  col 2: sorteo ID
  col 3: 14 signs + 1 pleno (all comma-separated)
  We can only extract 14 signs for these seasons.

LAYOUT D (modern 2021-22 to 2025-26): 5 cols
  col 0: "X Semana YYYY"
  col 1: jornada-in-week
  col 2: Q-DOMINGO / Q-LUNES / Q-JUEVES
  col 3: sorteo ID
  col 4: 15 signs + 1 pleno (all comma-separated)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

import xlrd  # type: ignore

DEFAULT_XLS = Path("data/raw/HistoricoQuiniela.xls")


def parse_xls(path: Path | str = DEFAULT_XLS) -> list[dict[str, Any]]:
    """Parse all sheets and return list of dicts."""
    wb = xlrd.open_workbook(str(path))
    rows = []
    for sname in wb.sheet_names():
        sh = wb.sheet_by_name(sname)
        if "MAPINFO" in sname.upper() or "ESRI" in sname.upper():
            continue
        # Determine season
        season = sname.replace("F", "").replace("D", "")  # 86_87F → 86_87
        season_start, season_end = _parse_season_name(season)
        if season_start is None:
            continue
        season_label = f"{season_start}-{str(season_end)[-2:].zfill(2)}"
        if sh.ncols == 51:
            sheet_rows = _parse_layout_b(sh, season_label, season_start)
        elif sh.ncols == 37:
            sheet_rows = _parse_layout_b(sh, season_label, season_start)
        elif sh.ncols == 4:
            sheet_rows = _parse_layout_c(sh, season_label, season_start)
        elif sh.ncols == 5:
            sheet_rows = _parse_layout_d(sh, season_label, season_start)
        else:
            sheet_rows = _parse_legacy_sheet(sh, season_label, season_start)
        rows.extend(sheet_rows)
    return rows


def _parse_season_name(name: str) -> tuple[int, int]:
    """'72_73' → (1972, 1973). '1996_97' → (1996, 2097)? No, see below."""
    parts = name.split("_")
    if len(parts) != 2:
        return (0, 0)
    a, b = parts
    try:
        sa = int(a)
        sb = int(b)
    except ValueError:
        return (0, 0)
    if sa < 100:
        # 2-digit year (1972-73 say 72_73)
        sa = 1900 + sa
    if sb < 100:
        # E.g. 91_92 → sb=92 (assuming sb > sa)
        if sa // 100 == sb // 100:
            sb = sa + 1
        else:
            sb = 1900 + sb
    return (sa, sb)


def _is_legitimate_sign(s) -> bool:
    if s in ("1", "X", "2"):
        return True
    # xlrd returns floats for numeric cells
    if isinstance(s, float) and s in (1.0, 2.0):
        return True
    return False


def _normalize_sign(s) -> str:
    """Convert sign to '1', 'X' or '2' regardless of input type."""
    if isinstance(s, float):
        return str(int(s))
    return str(s).strip()


def _parse_legacy_sheet(sh: "xlrd.sheet.Sheet", season: str, season_start: int) -> list[dict[str, Any]]:
    """LAYOUT A: 35 cols, 15 signs in cols 3-17."""
    rows = []
    data_start = None
    for r in range(sh.nrows):
        row = [sh.cell_value(r, c) for c in range(sh.ncols)]
        joined = " ".join(str(v) for v in row).lower()
        if "pronosticos" in joined or "pronósticos" in joined:
            data_start = r + 2
            break
    if data_start is None:
        data_start = 8

    for r in range(data_start, sh.nrows):
        row = [sh.cell_value(r, c) for c in range(sh.ncols)]
        if all(v == "" for v in row):
            continue
        try:
            jornada = int(row[1])
        except (ValueError, TypeError):
            continue
        signs: list[str] = []
        for c in range(3, 18):
            if c >= sh.ncols:
                break
            s = str(row[c]).strip()
            if _is_legitimate_sign(s):
                signs.append(s)
            else:
                break
        if len(signs) != 15:
            continue
        fecha_val = row[2] if len(row) > 2 else ""
        rows.append({
            "season": season,
            "season_start": season_start,
            "semana": "",
            "jornada": jornada,
            "dia": "",
            "sorteo": str(fecha_val).strip() if fecha_val else "",
            "signs": signs,
            "pleno": "",
        })
    return rows


def _parse_layout_b(sh: "xlrd.sheet.Sheet", season: str, season_start: int) -> list[dict[str, Any]]:
    """LAYOUT B (2014-2018): 51 cols, signs in cols 6-18, pleno in col 19, número in col 20.

    The XLS has 13 sign cells + 1 pleno cell + 1 number cell (not 15 signs).
    """
    rows = []
    data_start = 8
    for r in range(data_start, sh.nrows):
        row = [sh.cell_value(r, c) for c in range(sh.ncols)]
        if all(v == "" for v in row):
            continue
        try:
            jornada = int(float(row[1]))
        except (ValueError, TypeError):
            continue
        # 13 signs from cols 6-18 (col 19 is pleno, col 20 is number)
        signs: list[str] = []
        for c in range(6, 19):
            if c >= sh.ncols:
                break
            s = row[c]
            if _is_legitimate_sign(s):
                signs.append(_normalize_sign(s))
            else:
                break
        if len(signs) not in (13, 14, 15):
            continue
        # Pleno in col 19
        pleno = ""
        if 19 < sh.ncols:
            v = row[19]
            s = str(v).strip()
            if s and (("M" in s) or ("-" in s) or len(s) >= 2):
                pleno = s
            elif s in ("1", "X", "2"):
                pleno = s
        sorteo = str(row[2]).strip() if len(row) > 2 else ""
        rows.append({
            "season": season,
            "season_start": season_start,
            "semana": "",
            "jornada": jornada,
            "dia": "",
            "sorteo": sorteo,
            "signs": signs,
            "pleno": pleno,
        })
    return rows


def _parse_layout_c(sh: "xlrd.sheet.Sheet", season: str, season_start: int) -> list[dict[str, Any]]:
    """LAYOUT C (2019-2020): 4 cols, 14 signs + 1 pleno in col 3 (BUG: missing sign 15)."""
    rows = []
    data_start = 8
    for r in range(data_start, sh.nrows):
        row = [sh.cell_value(r, c) for c in range(sh.ncols)]
        if all(v == "" for v in row):
            continue
        combo = str(row[3]).strip()
        if not combo:
            continue
        parts = [s.strip() for s in combo.split(",")]
        # 14 signs + 1 pleno
        signs = [s for s in parts if _is_legitimate_sign(s)]
        if len(signs) < 14:
            continue
        signs = signs[:14]  # truncate to 14 (XLS bug: missing sign 15)
        last = parts[-1] if parts else ""
        pleno = last if (last and (len(last) >= 2 or "M" in last)) else ""
        # Sorteo from col 2
        sorteo = str(row[2]).strip()
        # Find jornada: col 0 has "X Semana YYYY" where X is intra-week id
        col0 = str(row[0]).strip()
        m = re.match(r"(\d+)\s+Semana\s+(\d+)", col0)
        jornada = int(m.group(1)) if m else 0
        rows.append({
            "season": season,
            "season_start": season_start,
            "semana": m.group(2) if m else "",
            "jornada": jornada,
            "dia": str(row[1]).strip() if len(row) > 1 else "",
            "sorteo": sorteo,
            "signs": signs,
            "pleno": pleno,
        })
    return rows


def _parse_layout_d(sh: "xlrd.sheet.Sheet", season: str, season_start: int) -> list[dict[str, Any]]:
    """LAYOUT D (2021-2025): 5 cols, 15 signs + 1 pleno in col 4."""
    rows = []
    data_start = 8
    for r in range(data_start, sh.nrows):
        row = [sh.cell_value(r, c) for c in range(sh.ncols)]
        if all(v == "" for v in row):
            continue
        combo = str(row[4]).strip()
        if not combo:
            continue
        parts = [s.strip() for s in combo.split(",")]
        # 15 signs + 1 pleno (last is pleno)
        signs = [s for s in parts[:-1] if _is_legitimate_sign(s)]
        if len(signs) != 15:
            continue
        pleno = parts[-1] if len(parts) == 16 else ""
        # Sorteo from col 3
        sorteo = str(row[3]).strip() if len(row) > 3 else ""
        col0 = str(row[0]).strip()
        m = re.match(r"(\d+)\s+Semana\s+(\d+)", col0)
        jornada = int(float(row[1])) if m else 0
        dia = str(row[2]).strip() if len(row) > 2 else ""
        rows.append({
            "season": season,
            "season_start": season_start,
            "semana": m.group(2) if m else "",
            "jornada": jornada,
            "dia": dia,
            "sorteo": sorteo,
            "signs": signs,
            "pleno": pleno,
        })
    return rows


def main():
    rows = parse_xls(DEFAULT_XLS)
    print(f"Total sorteos extraídos: {len(rows)}")
    seasons = {}
    for r in rows:
        seasons.setdefault(r["season"], 0)
        seasons[r["season"]] += 1
    print(f"Temporadas: {len(seasons)}")
    total_signs = sum(len(r["signs"]) for r in rows)
    print(f"Total signos: {total_signs}")
    # Muestra de los primeros y los últimos
    for r in rows[:3] + rows[-3:]:
        print(f"  {r['season']} J{r['jornada']:>3} - {r['sorteo']!s:>12} - {len(r['signs'])} signos: {r['signs']}")


if __name__ == "__main__":
    main()
