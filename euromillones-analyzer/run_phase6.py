"""Ejecuta el backtesting del notebook 03. Punto de entrada."""
import sys
sys.path.insert(0, '.')
from src.db.repository import SorteoRepository
from src.analysis.descriptive import to_dataframe
from src.analysis.backtest import backtest_completo, walk_forward_validation
from src.analysis.statistics import bonferroni, fdr_bh, holm
import json
import pandas as pd


def main():
    repo = SorteoRepository('data/euromillones.db')
    sorteos = repo.get_all()
    df = to_dataframe(sorteos)
    print(f"Total sorteos cargados: {len(df)}")

    print("\n" + "=" * 60)
    print("BACKTESTING RIGUROSO")
    print("=" * 60)
    result = backtest_completo(df, year_split=2021)

    print("\n" + "=" * 60)
    print("WALK-FORWARD VALIDATION")
    print("=" * 60)
    wf = walk_forward_validation(df, year_split=2021)
    print(f"Total validaciones: {len(wf)}")
    print(f"Siguen frios en test: {wf['sigue_frio'].sum()} / {len(wf)} ({wf['sigue_frio'].mean()*100:.1f}%)")

    # Guardar resultados
    summary = {
        "n_sorteos_total": len(df),
        "year_split": result["year_split"],
        "n_train": result["n_train"],
        "n_test": result["n_test"],
        "patrones_train_sin_correccion": result["patrones_train_sin_correccion"],
        "n_bonferroni": result["n_bonferroni"],
        "n_fdr": result["n_fdr"],
        "n_holm": result["n_holm"],
        "supervivientes": result["supervivientes"],
        "backtest": result["backtest_df"].to_dict(orient='records') if not result["backtest_df"].empty else [],
        "walk_forward_tasa_frios": float(wf["sigue_frio"].mean()),
        "walk_forward_n": len(wf),
    }

    with open('reports/backtest_resultados.json', 'w') as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"\nResultados guardados en reports/backtest_resultados.json")
    return summary


if __name__ == "__main__":
    main()
