"""Venue Bias: ¿son los campos 'trampa' realmente más difíciles para grandes visitantes?

Hipótesis popular: el Sadar, Anoeta, Mestalla, Pizjuán son 'campos trampa'
para los grandes (Real Madrid, Barcelona, Atlético).

Hipótesis alternativa (lo que vamos a validar): en realidad los grandes
visitantes GANAN MÁS de lo esperado en estos campos porque:
1. La presión del partido grande les activa
2. El equipo pequeño se 'bloquea' ante grande visitante

Output: ranking de campos con su % victoria visitante (grandes) vs baseline.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


# Mapeo correcto equipo → nombre en BD (verificado manualmente)
GRANDES = ["real_madrid", "barcelona", "ath_madrid"]
MEDIANOS = ["sevilla", "valencia", "athletic", "sociedad", "betis", "villareal", "espanyol"]

# (visitante, local) → etiquetas bonitas
FIJOS = [
    ("real_madrid", "osasuna", "El Sadar"),
    ("barcelona", "osasuna", "El Sadar"),
    ("ath_madrid", "osasuna", "El Sadar"),
    ("real_madrid", "sociedad", "Anoeta"),
    ("barcelona", "sociedad", "Anoeta"),
    ("ath_madrid", "sociedad", "Anoeta"),
    ("real_madrid", "sevilla", "Pizjuán"),
    ("barcelona", "sevilla", "Pizjuán"),
    ("ath_madrid", "sevilla", "Pizjuán"),
    ("real_madrid", "valencia", "Mestalla"),
    ("barcelona", "valencia", "Mestalla"),
    ("ath_madrid", "valencia", "Mestalla"),
    ("real_madrid", "betis", "Benito Villamarín"),
    ("barcelona", "betis", "Benito Villamarín"),
    ("ath_madrid", "betis", "Benito Villamarín"),
    ("real_madrid", "ath_bilbao", "San Mamés"),
    ("barcelona", "ath_bilbao", "San Mamés"),
    ("ath_madrid", "ath_bilbao", "San Mamés"),
    ("real_madrid", "villareal", "El Madrigal"),
    ("barcelona", "villareal", "El Madrigal"),
    ("ath_madrid", "villareal", "El Madrigal"),
    ("real_madrid", "celta", "Balaídos"),
    ("barcelona", "celta", "Balaídos"),
    ("real_madrid", "espanol", "RCDE Stadium"),
    ("barcelona", "espanol", "RCDE Stadium"),
    ("real_madrid", "mallorca", "Son Moix"),
    ("barcelona", "mallorca", "Son Moix"),
    ("real_madrid", "getafe", "Coliseum"),
    ("barcelona", "getafe", "Coliseum"),
    ("real_madrid", "alaves", "Mendizorroza"),
    ("barcelona", "alaves", "Mendizorroza"),
    ("real_madrid", "eibar", "Ipurua"),
    ("barcelona", "eibar", "Ipurua"),
    ("real_madrid", "elche", "Martínez Valero"),
    ("barcelona", "elche", "Martínez Valero"),
    ("real_madrid", "girona", "Montilivi"),
    ("barcelona", "girona", "Montilivi"),
    ("real_madrid", "vallecano", "Vallecas"),
    ("barcelona", "vallecano", "Vallecas"),
    ("real_madrid", "valladolid", "José Zorrilla"),
    ("barcelona", "valladolid", "José Zorrilla"),
    ("real_madrid", "levante", "Ciutat de València"),
    ("barcelona", "levante", "Ciutat de València"),
    ("real_madrid", "espanyol", "RCDE"),
    ("barcelona", "espanyol", "RCDE"),
]


def main() -> int:
    conn = sqlite3.connect(ROOT / "data" / "quiniela.db")
    pd = __import__("pandas")

    # Baseline
    n_total = conn.execute("SELECT COUNT(*) FROM matches WHERE result IS NOT NULL").fetchone()[0]
    n_away = conn.execute("SELECT COUNT(*) FROM matches WHERE result='A'").fetchone()[0]
    n_draw = conn.execute("SELECT COUNT(*) FROM matches WHERE result='D'").fetchone()[0]
    n_home = conn.execute("SELECT COUNT(*) FROM matches WHERE result='H'").fetchone()[0]
    base_away = n_away / n_total
    print(f"=== Baseline global ===")
    print(f"  Local:    {n_home/n_total:.3f} ({100*n_home/n_total:.1f}%)")
    print(f"  Empate:   {n_draw/n_total:.3f} ({100*n_draw/n_total:.1f}%)")
    print(f"  Visitante:{base_away:.3f} ({100*base_away:.1f}%)")
    print()

    # Tabla con datos
    rows = []
    for away, home, label in FIJOS:
        r = conn.execute(
            """
            SELECT COUNT(*) AS n,
                   SUM(CASE WHEN result='A' THEN 1 ELSE 0 END) AS wins,
                   SUM(CASE WHEN result='D' THEN 1 ELSE 0 END) AS draws,
                   SUM(CASE WHEN result='H' THEN 1 ELSE 0 END) AS losses
            FROM matches WHERE away_team=? AND home_team=?
            """,
            (away, home),
        ).fetchone()
        n, w, d, l = r
        if n == 0:
            continue
        rows.append({
            "away_team": away, "home_team": home, "campo": label,
            "n": n, "wins_away": w, "draws": d, "losses_away": l,
            "win_pct": 100*w/n, "draw_pct": 100*d/n, "loss_pct": 100*l/n,
            "delta": w/n - base_away,
        })
    df = pd.DataFrame(rows)
    print(f"Partidos cargados: {len(df)} (de {len(FIJOS)} casos)")
    print()

    # Análisis por visitante grande
    for grande in GRANDES:
        sub = df[df["away_team"] == grande].copy().sort_values("win_pct")
        print(f"=== {grande.upper()} como visitante ===")
        print(f"  {'Campo':25s}  n  W%    D%    L%    delta")
        for _, r in sub.iterrows():
            flag = " ❌ TRAMPA" if r["win_pct"] < 20 else (" ✅ gallina" if r["win_pct"] > 50 else "   ~normal")
            print(f"  {r['campo']:25s}  {int(r['n']):2d}  {r['win_pct']:5.1f}  {r['draw_pct']:5.1f}  {r['loss_pct']:5.1f}  {r['delta']:+.3f}{flag}")
        print()

    # Ranking global: campos más "trampa" para grandes
    print("=== RANKING CAMPOS TRAMPA para grandes (avg win% visitante, n total >= 30) ===")
    agg = df.groupby("campo").agg(
        total_n=("n", "sum"),
        wins=("wins_away", "sum"),
        losses=("losses_away", "sum"),
    ).reset_index()
    # avg_win_pct es RATIO decimal (0-1), no porcentaje
    agg["avg_win_pct"] = agg["wins"] / agg["total_n"]
    agg["avg_loss_pct"] = agg["losses"] / agg["total_n"]
    agg = agg[agg["total_n"] >= 30].sort_values("avg_win_pct")
    for _, r in agg.iterrows():
        delta = r["avg_win_pct"] - base_away
        flag = " ❌ TRAMPA" if delta < -0.05 else (" 🐔 gallina" if delta > 0.15 else " ~normal")
        print(f"  {r['campo']:25s}  total_n={int(r['total_n']):3d}  W%={100*r['avg_win_pct']:5.1f}  L%={100*r['avg_loss_pct']:5.1f}  delta={delta:+.3f}{flag}")
    return 0


if __name__ == "__main__":
    sys.exit(main())