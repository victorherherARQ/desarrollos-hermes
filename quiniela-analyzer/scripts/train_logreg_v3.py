"""Entrena LogReg v3 con todas las features (odds + form + h2h + rest).

Walk-forward validation temporal: para cada temporada test (2526, 2425,
2324, 2223, 2122, 2021), entrena con todas las temporadas ANTERIORES y mide
accuracy en la test season. Repite y promedia.

Comparación:
  - Baseline local (siempre H): ~46%
  - AvgH argmax: 51.27% (Task 1)
  - LogReg v3: ¿superará ambos?
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
PARQUET = ROOT / "data" / "training_set_v3.parquet"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)


FEATURE_COLS = [
    # Odds
    "imp_h", "imp_d", "imp_a", "avg_h", "avg_d", "avg_a",
    "psc_h", "psc_d", "psc_a",
    # Form n=5
    "home_n5_w", "home_n5_d", "home_n5_l",
    "away_n5_w", "away_n5_d", "away_n5_l",
    # Form n=10
    "home_n10_wins", "home_n10_points_avg",
    "away_n10_wins", "away_n10_points_avg",
    # Form streaks
    "home_win_streak", "away_unbeaten_streak",
    "form_diff_n5", "form_diff_n10",
    # H2H
    "h2h5_home_wins", "h2h5_draws", "h2h5_away_wins",
    "h2h10_home_wins", "h2h10_draws", "h2h10_away_wins",
    # Rest
    "rest_days_home", "rest_days_away", "rest_days_diff",
]

TEST_SEASONS = ["2425", "2526"]  # Test seasons (excluimos 1920/2021/2122/2223/2324 por cleanliness)


def avg_h_argmax_pred(df: pd.DataFrame) -> np.ndarray:
    """Baseline AvgH argmax."""
    h = 1.0 / df["avg_h"]
    d = 1.0 / df["avg_d"]
    a = 1.0 / df["avg_a"]
    s = h + d + a
    h, d, a = h / s, d / s, a / s
    pred = np.where(h >= d, np.where(h >= a, "H", "A"), np.where(d >= a, "D", "A"))
    return pred


def baseline_local_pred(df: pd.DataFrame) -> np.ndarray:
    """Baseline: siempre H."""
    return np.array(["H"] * len(df))


def evaluate_walk_forward(df: pd.DataFrame) -> dict:
    """Walk-forward temporal: cada test_season con train en TODAS las anteriores."""
    results = {}
    seasons = sorted(df["season"].unique())

    for test_season in TEST_SEASONS:
        if test_season not in seasons:
            continue

        train_seasons = [s for s in seasons if s < test_season]
        if not train_seasons:
            continue

        log.info(f"\n=== Test season: {test_season} (train: {train_seasons}) ===")

        train = df[df["season"].isin(train_seasons)].copy()
        test = df[df["season"] == test_season].copy()

        # Drop partidos con NaN en features
        train = train.dropna(subset=FEATURE_COLS)
        test = test.dropna(subset=FEATURE_COLS)

        X_train = train[FEATURE_COLS].values
        y_train = train["result"].values
        X_test = test[FEATURE_COLS].values
        y_test = test["result"].values

        # Scale
        scaler = StandardScaler()
        X_train_s = scaler.fit_transform(X_train)
        X_test_s = scaler.transform(X_test)

        # Train LogReg
        model = LogisticRegression(max_iter=1000, C=1.0)
        model.fit(X_train_s, y_train)

        # Predict
        pred_lr = model.predict(X_test_s)
        acc_lr = (pred_lr == y_test).mean()

        # AvgH baseline
        pred_avg = avg_h_argmax_pred(test)
        acc_avg = (pred_avg == y_test).mean()

        # Local baseline
        pred_local = baseline_local_pred(test)
        acc_local = (pred_local == y_test).mean()

        # Top features (LogReg coefficients)
        coefs = pd.DataFrame({
            "feature": FEATURE_COLS,
            "coef_H": model.coef_[0],
            "coef_D": model.coef_[1],
            "coef_A": model.coef_[2],
        }).sort_values("coef_H", key=abs, ascending=False)

        results[test_season] = {
            "n_test": len(test),
            "acc_lr": acc_lr,
            "acc_avg": acc_avg,
            "acc_local": acc_local,
            "delta_vs_avg": acc_lr - acc_avg,
            "delta_vs_local": acc_lr - acc_local,
            "top_features": coefs.head(10).to_dict("records"),
        }

        log.info(f"  LogReg v3:  {acc_lr:.4f}  (n={len(test)})")
        log.info(f"  AvgH:       {acc_avg:.4f}")
        log.info(f"  Local:      {acc_local:.4f}")
        log.info(f"  Δ vs AvgH:  {results[test_season]['delta_vs_avg']:+.4f}")
        log.info(f"  Δ vs Local: {results[test_season]['delta_vs_local']:+.4f}")

    return results


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--parquet", default=str(PARQUET))
    args = p.parse_args()

    log.info(f"Cargando {args.parquet}...")
    df = pd.read_parquet(args.parquet)
    log.info(f"Loaded {df.shape[0]} partidos × {df.shape[1]} cols")

    # Resultado global
    results = evaluate_walk_forward(df)

    # Resumen
    print("\n" + "=" * 70)
    print("RESUMEN WALK-FORWARD TEMPORAL")
    print("=" * 70)
    print(f"{'Test season':<12} {'n':<5} {'LogReg':<8} {'AvgH':<8} {'Local':<8} {'Δ vs AvgH':<12} {'Δ vs Local'}")
    print("-" * 70)
    for s, r in results.items():
        print(f"{s:<12} {r['n_test']:<5} {r['acc_lr']:<8.4f} {r['acc_avg']:<8.4f} {r['acc_local']:<8.4f} "
              f"{r['delta_vs_avg']:+.4f}       {r['delta_vs_local']:+.4f}")

    avg_lr = np.mean([r["acc_lr"] for r in results.values()])
    avg_avg = np.mean([r["acc_avg"] for r in results.values()])
    avg_local = np.mean([r["acc_local"] for r in results.values()])
    print("-" * 70)
    print(f"{'PROMEDIO':<12} {'':<5} {avg_lr:<8.4f} {avg_avg:<8.4f} {avg_local:<8.4f} "
          f"{avg_lr - avg_avg:+.4f}       {avg_lr - avg_local:+.4f}")

    # Go/No-Go
    delta_vs_avg = avg_lr - avg_avg
    delta_vs_local = avg_lr - avg_local
    print("\n" + "=" * 70)
    print("GO/NO-GO BINARIO")
    print("=" * 70)
    print(f"LogReg v3 vs AvgH: {delta_vs_avg:+.4f}  "
          f"{'✅ GO' if delta_vs_avg >= 0.01 else '❌ NO-GO'} (umbral +1pp)")
    print(f"LogReg v3 vs Local: {delta_vs_local:+.4f}  "
          f"{'✅ GO' if delta_vs_local >= 0.01 else '❌ NO-GO'}")

    # Top features del último training
    if results:
        last = list(results.values())[-1]
        print(f"\nTop 10 features (test season {list(results.keys())[-1]}):")
        for f in last["top_features"]:
            print(f"  {f['feature']:25s}  H={f['coef_H']:+.3f}  D={f['coef_D']:+.3f}  A={f['coef_A']:+.3f}")


if __name__ == "__main__":
    main()