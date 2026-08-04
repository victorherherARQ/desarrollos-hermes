"""Odds features: cuotas de mercado como señal predictiva.

Tres señales disponibles (cobertura medida en seed_odds.py — 16 temporadas):

  avg_h/d/a       AvgH/AvgD/AvgA   cuota promedio del mercado completo
                                  — solo 9 temporadas (~44.6%) — 2016-17 a 2025-26
  psc_h/d/a       PSCH/PSCD/PSCA   Pinnacle (sharp book, profesionales)
                                  — 10.809 filas (~83.6%) — 5 temporadas
  b365c_h/d/a     B365CH/D/A       Bet365 closing odds
                                  — 5.768 filas (~44.6%) — 5 temporadas

La señal Avg-implied YA SUPERA al baseline always_H (49.83% vs 44.80% en 5.768 partidos).

Pipeline:
    odds_for_match(conn, season, division, home, away, matchday_date)
        → dict con cuotas raw + probabilidades implícitas normalizadas
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "quiniela.db"


def implied_probs(h: float | None, d: float | None, a: float | None) -> tuple[float | None, float | None, float | None, float | None]:
    """Convierte cuotas decimales (1/X/2) en probabilidades implícitas normalizadas.

    Quitar el overround: t = 1/h + 1/d + 1/a. p_X = (1/X) / t.

    Returns
    -------
    (p_h, p_d, p_a, overround)
        None en cualquier componente si las cuotas no son utilizables.
    """
    if h is None or d is None or a is None:
        return None, None, None, None
    if h <= 1.0 or d <= 1.0 or a <= 1.0:
        return None, None, None, None
    try:
        ih, id_, ia = 1.0 / h, 1.0 / d, 1.0 / a
    except ZeroDivisionError:
        return None, None, None, None
    t = ih + id_ + ia
    if t <= 0 or t > 2.0:
        # overround > 100% → cuotas corruptas
        return None, None, None, None
    return ih / t, id_ / t, ia / t, t


def odds_for_match(
    conn: sqlite3.Connection,
    *,
    season: str,
    division: str,
    home_team: str,
    away_team: str,
    matchday_date: str,
) -> dict:
    """Lee las cuotas almacenadas para un partido y devuelve features normalizadas.

    Parameters
    ----------
    season : str
        '2526', '2425', etc.
    division : str
        'SP1' o 'SP2'.
    home_team, away_team : str
        team_id (slug, ej 'real_madrid', 'ath_madrid').
    matchday_date : str
        'YYYY-MM-DD'.

    Returns
    -------
    dict
        Posibles claves (todas presentes, con None si no hay dato):

        - raw_avg_h/d/a         : cuotas promedio del mercado
        - raw_max_h/d/a         : cuotas máximas del mercado
        - raw_psc_h/d/a         : Pinnacle (sharp book)
        - raw_b365c_h/d/a       : Bet365 closing
        - imp_avg_h/d/a         : prob implícita desde avg (normalizada, sin overround)
        - imp_b365c_h/d/a       : prob implícita desde Bet365 closing
        - overround_avg         : t = 1/h+1/d+1/a de avg
        - overround_b365c       : t de Bet365 closing
        - market_source         : 'avg' | 'psc+b365c' | 'psc' | 'b365c' | None
    """
    row = conn.execute(
        """
        SELECT avg_h, avg_d, avg_a,
               max_h, max_d, max_a,
               psc_h, psc_d, psc_a,
               b365c_h, b365c_d, b365c_a
        FROM match_odds
        WHERE season = ? AND division = ?
          AND home_team = ? AND away_team = ?
          AND matchday_date = ?
        """,
        (season, division, home_team, away_team, matchday_date),
    ).fetchone()

    out: dict = {}

    if row is None:
        # No hay cuotas para este partido
        out["market_source"] = None
        return out

    avg_h, avg_d, avg_a, max_h, max_d, max_a, psc_h, psc_d, psc_a, b365c_h, b365c_d, b365c_a = row

    # Raw cuotas
    out["raw_avg_h"] = avg_h
    out["raw_avg_d"] = avg_d
    out["raw_avg_a"] = avg_a
    out["raw_max_h"] = max_h
    out["raw_max_d"] = max_d
    out["raw_max_a"] = max_a
    out["raw_psc_h"] = psc_h
    out["raw_psc_d"] = psc_d
    out["raw_psc_a"] = psc_a
    out["raw_b365c_h"] = b365c_h
    out["raw_b365c_d"] = b365c_d
    out["raw_b365c_a"] = b365c_a

    # Implied probs (avg)
    if avg_h and avg_d and avg_a:
        ph, pd_, pa, over = implied_probs(avg_h, avg_d, avg_a)
        out["imp_avg_h"] = ph
        out["imp_avg_d"] = pd_
        out["imp_avg_a"] = pa
        out["overround_avg"] = over

    # Implied probs (Bet365 closing)
    if b365c_h and b365c_d and b365c_a:
        ph, pd_, pa, over = implied_probs(b365c_h, b365c_d, b365c_a)
        out["imp_b365c_h"] = ph
        out["imp_b365c_d"] = pd_
        out["imp_b365c_a"] = pa
        out["overround_b365c"] = over

    # Implied probs (Pinnacle — sharp book, NO normalizamos con overround porque
    # Pinnacle suele tener margen bajo y la señal "true" es prácticamente la cuota directa)
    if psc_h and psc_d and psc_a:
        ph, pd_, pa, over = implied_probs(psc_h, psc_d, psc_a)
        out["imp_psc_h"] = ph
        out["imp_psc_d"] = pd_
        out["imp_psc_a"] = pa
        out["overround_psc"] = over

    # Determinar fuente primaria para el modelo: avg > psc > b365c
    if avg_h and avg_d and avg_a:
        out["market_source"] = "avg"
    elif psc_h and psc_d and psc_a:
        out["market_source"] = "psc"
    elif b365c_h and b365c_d and b365c_a:
        out["market_source"] = "b365c"
    else:
        out["market_source"] = None

    return out


# ── Smoke test ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    print("=== Test 1: Valencia vs Betis (1-1, 09/11/2025) ===")
    out = odds_for_match(
        conn,
        season="2526", division="SP1",
        home_team="valencia", away_team="betis",
        matchday_date="2025-11-09",
    )
    for k, v in out.items():
        if isinstance(v, float):
            print(f"  {k:20s} = {v:.4f}")
        else:
            print(f"  {k:20s} = {v}")

    print()
    print("=== Test 2: Real Madrid vs Barcelona (2024-10-26, el clásico) ===")
    out = odds_for_match(
        conn,
        season="2425", division="SP1",
        home_team="real_madrid", away_team="barcelona",
        matchday_date="2024-10-26",
    )
    for k, v in out.items():
        if isinstance(v, float):
            print(f"  {k:20s} = {v:.4f}")
        else:
            print(f"  {k:20s} = {v}")

    print()
    print("=== Test 3: Partido sin cuotas (debería devolver market_source=None) ===")
    out = odds_for_match(
        conn,
        season="1011", division="SP1",
        home_team="levante", away_team="vallecano",
        matchday_date="2010-08-29",
    )
    print(f"  market_source = {out.get('market_source')}")
    print(f"  keys devueltas = {list(out.keys())}")

    conn.close()
