"""Valida hipótesis de 'venue bias': campos históricamente incómodos para un visitante.

Para cada (away_team, home_team) fijo (no simétrico), mide el % de victorias
del visitante y compara contra su baseline.

Casos famosos a validar:
  - Real Madrid visitando El Sadar (Osasuna)
  - Barcelona visitando Anoeta (Real Sociedad)

Hipótesis: los grandes pierden más de lo esperado en estos campos 'trampa'.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    conn = sqlite3.connect(ROOT / "data" / "quiniela.db")
    pd = __import__("pandas")

    # 1) Tabla general (away_team, home_team) → stats
    rows = conn.execute(
        """
        SELECT away_team, home_team, COUNT(*) AS n,
               SUM(CASE WHEN result='A' THEN 1 ELSE 0 END) AS wins_away,
               SUM(CASE WHEN result='D' THEN 1 ELSE 0 END) AS draws,
               SUM(CASE WHEN result='H' THEN 1 ELSE 0 END) AS losses_away
        FROM matches
        WHERE result IS NOT NULL
        GROUP BY away_team, home_team
        HAVING n >= 5
        """,
    ).fetchall()
    cols = ["away_team", "home_team", "n", "wins_away", "draws", "losses_away"]
    df = pd.DataFrame(rows, columns=cols)
    df["win_rate_away"] = df["wins_away"] / df["n"]
    df["draw_rate"] = df["draws"] / df["n"]
    df["loss_rate_away"] = df["losses_away"] / df["n"]

    # Baseline: ¿qué % de partidos gana el visitante en general?
    n_total = conn.execute("SELECT COUNT(*) FROM matches WHERE result IS NOT NULL").fetchone()[0]
    n_home_w = conn.execute("SELECT COUNT(*) FROM matches WHERE result='H'").fetchone()[0]
    n_away_w = conn.execute("SELECT COUNT(*) FROM matches WHERE result='A'").fetchone()[0]
    n_draw = conn.execute("SELECT COUNT(*) FROM matches WHERE result='D'").fetchone()[0]
    baseline_away = n_away_w / n_total
    baseline_home = n_home_w / n_total
    baseline_draw = n_draw / n_total
    print(f"=== Baseline ===")
    print(f"  Local gana globalmente: {baseline_home:.3f} ({100*baseline_home:.1f}%)")
    print(f"  Empate:                 {baseline_draw:.3f} ({100*baseline_draw:.1f}%)")
    print(f"  Visitante gana:         {baseline_away:.3f} ({100*baseline_away:.1f}%)")
    print()

    # 2) Casos específicos del usuario
    cases = [
        ("real_madrid", "osasuna", "Real Madrid → El Sadar (Osasuna)"),
        ("barcelona", "real_sociedad", "Barcelona → Anoeta (Real Sociedad)"),
        # Bonus para comparar
        ("real_madrid", "real_sociedad", "Real Madrid → Anoeta"),
        ("barcelona", "osasuna", "Barcelona → El Sadar"),
        ("real_madrid", "sevilla", "Real Madrid → Pizjuán"),
        ("barcelona", "sevilla", "Barcelona → Pizjuán"),
        ("real_madrid", "valencia", "Real Madrid → Mestalla"),
        ("barcelona", "valencia", "Barcelona → Mestalla"),
        ("real_madrid", "betis", "Real Madrid → Benito Villamarín"),
        ("barcelona", "betis", "Barcelona → Benito Villamarín"),
    ]
    print("=== Casos específicos ===")
    for away, home, label in cases:
        sub = df[(df["away_team"] == away) & (df["home_team"] == home)]
        if len(sub) == 0:
            print(f"  {label}: SIN DATOS (¿no se enfrentaron?)")
            continue
        r = sub.iloc[0]
        delta = r["win_rate_away"] - baseline_away
        flag = "❌ TRAMPA" if r["win_rate_away"] < baseline_away * 0.5 else "✓ normal"
        print(
            f"  {label}: n={int(r['n']):2d}  "
            f"win%={100*r['win_rate_away']:5.1f}%  "
            f"draw%={100*r['draw_rate']:5.1f}%  "
            f"loss%={100*r['loss_rate_away']:5.1f}%  "
            f"delta={delta:+.3f}  {flag}"
        )
    print()

    # 3) Ranking TOP-20: visitante con PEOR win_rate (mínimo 8 partidos)
    print("=== TOP-20 visitante con PEOR win_rate (n≥8) ===")
    worst = df[df["n"] >= 8].sort_values("win_rate_away").head(20)
    for _, r in worst.iterrows():
        delta = r["win_rate_away"] - baseline_away
        print(
            f"  {r['away_team']:18s} → {r['home_team']:18s}  "
            f"n={int(r['n']):2d}  win%={100*r['win_rate_away']:5.1f}%  "
            f"draw%={100*r['draw_rate']:5.1f}%  delta={delta:+.3f}"
        )
    print()

    # 4) Ranking TOP-10: visitante con MEJOR win_rate (mínimo 8 partidos)
    print("=== TOP-10 visitante con MEJOR win_rate (n≥8) ===")
    best = df[df["n"] >= 8].sort_values("win_rate_away", ascending=False).head(10)
    for _, r in best.iterrows():
        print(
            f"  {r['away_team']:18s} → {r['home_team']:18s}  "
            f"n={int(r['n']):2d}  win%={100*r['win_rate_away']:5.1f}%  "
            f"draw%={100*r['draw_rate']:5.1f}%  "
        )
    print()

    # 5) ¿Cuántos (visitante→campo) tienen suficiente muestra?
    print(f"=== Distribución de muestra por par (away,home) ===")
    n_pairs_5 = (df["n"] >= 5).sum()
    n_pairs_8 = (df["n"] >= 8).sum()
    n_pairs_15 = (df["n"] >= 15).sum()
    print(f"  Pares con n≥5: {n_pairs_5}")
    print(f"  Pares con n≥8: {n_pairs_8}")
    print(f"  Pares con n≥15: {n_pairs_15}")
    print()

    # 6) Para los "grandes" visitantes, ¿qué campos tienen < 30% victoria?
    grandes_visitantes = ["real_madrid", "barcelona", "atletico_madrid"]
    print("=== Campos 'trampa' para grandes visitantes (win_rate < 30%, n≥5) ===")
    for gv in grandes_visitantes:
        sub = df[(df["away_team"] == gv) & (df["n"] >= 5) & (df["win_rate_away"] < 0.30)]
        if len(sub) == 0:
            print(f"  {gv}: SIN campos trampa (< 30%)")
            continue
        for _, r in sub.sort_values("win_rate_away").iterrows():
            print(
                f"  {gv} → {r['home_team']:18s}  n={int(r['n']):2d}  "
                f"win%={100*r['win_rate_away']:5.1f}%  "
                f"draw%={100*r['draw_rate']:5.1f}%"
            )

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())