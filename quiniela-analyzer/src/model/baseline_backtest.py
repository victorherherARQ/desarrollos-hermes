"""Baseline prediction strategy backtest on quiniela_resultados.

Backtesteamos múltiples estrategias **jornada a jornada, temporada a temporada**,
incrementando el "knowledge" del modelo sólo con los datos anteriores (no miramos
el futuro, simulamos producción real).

Estrategias:
- ALWAYS_1, ALWAYS_X, ALWAYS_2 (ingenuas)
- MOST_FREQ_GLOBAL: distribución acumulada de signos históricos
- MOST_FREQ_LAST_5 / LAST_20: distribución de últimas N jornadas
- DIST_PER_NJORNADA: pred=1 si la frecuencia de 1 en la muestra > 50%, X si >33%, etc.

Reportes:
- Total hits / total partidos por estrategia
- % acierto por temporada
- % acierto cada K jornadas (snapshots incremental)
- Curva de evolución desde jornada 1
"""
from __future__ import annotations

import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

DB_PATH = Path("data/quiniela.db")
SIGNS = ("1", "X", "2")


def fetch_all_jornadas() -> list[dict]:
    """Return [{season_start, season, jornada, signs:[15], dia, fecha}] ordered."""
    c = sqlite3.connect(DB_PATH).cursor()
    rows = c.execute("""
        SELECT season_start, season, jornada, s1, s2, s3, s4, s5, s6, s7, s8, s9, s10, s11, s12, s13, s14, s15
        FROM quiniela_resultados
        ORDER BY season_start, CAST(jornada AS INTEGER)
    """).fetchall()
    out = []
    for r in rows:
        ss_start, season, jornada = r[0], r[1], r[2]
        signs = [s for s in r[3:] if s in SIGNS]
        if len(signs) == 15:
            out.append({
                "season_start": ss_start,
                "season": season,
                "jornada": jornada,
                "signs": signs,
            })
    return out


def predict_most_freq_global(history_signs: list[str]) -> str:
    if not history_signs:
        return "1"
    return Counter(history_signs).most_common(1)[0][0]


def predict_most_freq_recent(history: list[dict], idx: int, window: int) -> str:
    recent_signs = []
    for i in range(max(0, idx - window), idx):
        recent_signs.extend(history[i]["signs"])
    if not recent_signs:
        return "1"
    return Counter(recent_signs).most_common(1)[0][0]


def predict_historical_season_pattern(history_in_season: list[list[str]], idx_in_season: int) -> str:
    """Mira la distribución de signos en ESTA temporada hasta antes de la jornada idx_in_season."""
    flat = []
    for j in range(idx_in_season):
        flat.extend(history_in_season[j])
    if not flat:
        return "1"
    return Counter(flat).most_common(1)[0][0]


def score_pred(pred: str, target: list[str]) -> int:
    return sum(1 for t in target if t == pred)


def backtest() -> dict:
    history = fetch_all_jornadas()
    n = len(history)
    if n == 0:
        return {"error": "No hay jornadas en quiniela_resultados"}

    # Group by season for per-season analytics
    by_season: dict[str, list[dict]] = defaultdict(list)
    for j in history:
        by_season[j["season"]].append(j)

    # Per-jornada results
    per_jornada = []
    running_signs = []  # all signs seen so far ACROSS all seasons
    season_running_signs: dict[str, list[str]] = defaultdict(list)

    for idx, j in enumerate(history):
        season = j["season"]
        target = j["signs"]
        preds = {
            "always_1": "1",
            "always_X": "X",
            "always_2": "2",
            "most_freq_global": predict_most_freq_global(running_signs),
            "most_freq_last_5": predict_most_freq_recent(history, idx, 5),
            "most_freq_last_20": predict_most_freq_recent(history, idx, 20),
            "most_freq_in_season": predict_most_freq_global(season_running_signs[season]),
        }
        hits = {k: score_pred(v, target) for k, v in preds.items()}
        per_jornada.append({
            "idx": idx,
            "season": season,
            "jornada": j["jornada"],
            "n": len(target),
            "preds": preds,
            "hits": hits,
            "actual": target,
        })
        running_signs.extend(target)
        season_running_signs[season].extend(target)

    # Aggregate
    strategies = list(per_jornada[0]["preds"].keys())
    agg = {s: {"hits": 0, "total": 0} for s in strategies}
    for p in per_jornada:
        for s in strategies:
            agg[s]["hits"] += p["hits"][s]
            agg[s]["total"] += p["n"]

    # Per season
    per_season = {s: {strat: {"hits": 0, "total": 0} for strat in strategies} for s in by_season}
    for p in per_jornada:
        for s in strategies:
            per_season[p["season"]][s]["hits"] += p["hits"][s]
            per_season[p["season"]][s]["total"] += p["n"]

    # Incremental evolution (snapshots every K jornadas)
    snapshots = {K: [] for K in [5, 10, 20, 50]}
    cumul = {s: {"hits": 0, "total": 0} for s in strategies}
    for p in per_jornada:
        for s in strategies:
            cumul[s]["hits"] += p["hits"][s]
            cumul[s]["total"] += p["n"]
        for K in snapshots:
            if (p["idx"] + 1) % K == 0:
                snapshots[K].append({
                    "idx": p["idx"] + 1,
                    "season": p["season"],
                    "jornada": p["jornada"],
                    **{s: cumul[s]["hits"] / cumul[s]["total"] * 100 for s in strategies}
                })

    return {
        "history_size": n,
        "agg": agg,
        "per_season": per_season,
        "per_jornada": per_jornada,
        "snapshots": snapshots,
        "strategies": strategies,
    }


def render_report(out: dict) -> str:
    """Pretty-print a markdown report."""
    n = out["history_size"]
    lines = []
    lines.append(f"# Backtest — Quiniela baseline ({n} jornadas)")
    lines.append("")
    lines.append(f"Total jornadas: **{n}** ({n * 15} partidos)")
    lines.append("")
    lines.append("## Acierto por estrategia (acumulado)")
    lines.append("")
    lines.append("| Estrategia | Aciertos | Total | % Acierto |")
    lines.append("|---|---:|---:|---:|")
    for s in out["strategies"]:
        r = out["agg"][s]
        pct = r["hits"] / r["total"] * 100 if r["total"] else 0
        lines.append(f"| `{s}` | {r['hits']} | {r['total']} | {pct:.2f}% |")
    lines.append("")

    lines.append("## Acierto por temporada (most_freq_global)")
    lines.append("")
    lines.append("| Temporada | Aciertos | Total | % |")
    lines.append("|---|---:|---:|---:|")
    for s in sorted(out["per_season"].keys()):
        r = out["per_season"][s]["most_freq_global"]
        pct = r["hits"] / r["total"] * 100 if r["total"] else 0
        lines.append(f"| {s} | {r['hits']} | {r['total']} | {pct:.2f}% |")
    lines.append("")

    lines.append("## Evolución incremental (cada 5 jornadas)")
    lines.append("")
    lines.append("| Jornada | Temporada | most_freq_global | most_freq_last_5 | most_freq_in_season | always_1 |")
    lines.append("|---:|---|---|---:|---:|---:|")
    for snap in out["snapshots"][5][-30:]:
        lines.append(
            f"| {snap['idx']} | {snap['season']} (J{snap['jornada']}) | "
            f"{snap['most_freq_global']:.2f}% | {snap['most_freq_last_5']:.2f}% | "
            f"{snap['most_freq_in_season']:.2f}% | {snap['always_1']:.2f}% |"
        )
    if len(out["snapshots"][5]) > 30:
        lines.append("| ... | ... | ... | ... | ... | ... |")
        for snap in out["snapshots"][5][:5]:
            lines.append(
                f"| {snap['idx']} | {snap['season']} (J{snap['jornada']}) | "
                f"{snap['most_freq_global']:.2f}% | {snap['most_freq_last_5']:.2f}% | "
                f"{snap['most_freq_in_season']:.2f}% | {snap['always_1']:.2f}% |"
            )
    lines.append("")

    # Detectar punto de inflexión: a partir de qué jornada most_freq_global se mantiene por encima de always_1
    lines.append("## Punto de inflexión: ¿en qué jornada el modelo empieza a superar baseline?")
    lines.append("")
    cumul = {s: {"hits": 0, "total": 0} for s in out["strategies"]}
    pj = out["per_jornada"]
    crossover_idx = None
    for i, p in enumerate(pj):
        for s in out["strategies"]:
            cumul[s]["hits"] += p["hits"][s]
            cumul[s]["total"] += p["n"]
        if cumul["most_freq_global"]["total"] > 0:
            mfg = cumul["most_freq_global"]["hits"] / cumul["most_freq_global"]["total"]
            a1 = cumul["always_1"]["hits"] / cumul["always_1"]["total"]
            if i >= 10 and crossover_idx is None and mfg > a1 + 0.01:
                crossover_idx = i
                lines.append(f"  Primera jornada donde `most_freq_global` > `always_1` +1%: **jornada {i+1}** ({pj[i]['season']} J{pj[i]['jornada']})")
                break
    if crossover_idx is None:
        lines.append("  `most_freq_global` NUNCA supera `always_1` +1% en todo el histórico.")
    lines.append("")

    return "\n".join(lines)


def main():
    out = backtest()
    report = render_report(out)
    print(report)
    # Save
    Path("data/reports").mkdir(parents=True, exist_ok=True)
    Path("data/reports/baseline_backtest.md").write_text(report)
    print(f"\n💾 Reporte guardado: data/reports/baseline_backtest.md")


if __name__ == "__main__":
    main()
