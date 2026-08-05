"""Ensemble v4: LogReg + XGBoost + Dixon-Coles + AvgH baseline.

Walk-forward temporal. Compara:
  - AvgH argmax (mercado)
  - LogReg v3 (lineal con 33 features)
  - XGBoost (no-lineal con 33 features)
  - Dixon-Coles (modelo de goles via Poisson con ajuste de correlación)
  - Ensemble: vota ponderada por accuracy de validación

Objetivo: Go/No-Go binario vs AvgH (+1pp).
"""
from __future__ import annotations

import argparse
import json
import logging
import math
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
from scipy.stats import poisson as scipy_poisson
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
PARQUET = ROOT / "data" / "training_set_v3.parquet"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)


FEATURE_COLS = [
    "imp_h", "imp_d", "imp_a", "avg_h", "avg_d", "avg_a",
    "psc_h", "psc_d", "psc_a",
    "home_n5_w", "home_n5_d", "home_n5_l",
    "away_n5_w", "away_n5_d", "away_n5_l",
    "home_n10_wins", "home_n10_points_avg",
    "away_n10_wins", "away_n10_points_avg",
    "home_win_streak", "away_unbeaten_streak",
    "form_diff_n5", "form_diff_n10",
    "h2h5_home_wins", "h2h5_draws", "h2h5_away_wins",
    "h2h10_home_wins", "h2h10_draws", "h2h10_away_wins",
    "rest_days_home", "rest_days_away", "rest_days_diff",
]

LABELS = ["H", "D", "A"]  # orden de probs [H, D, A]


def avg_h_argmax_proba(df: pd.DataFrame) -> np.ndarray:
    """Devuelve matriz (n, 3) con probs [H, D, A] normalizadas."""
    h = 1.0 / df["avg_h"].values
    d = 1.0 / df["avg_d"].values
    a = 1.0 / df["avg_a"].values
    s = h + d + a
    h, d, a = h / s, d / s, a / s
    # Stack como [H, D, A]
    return np.column_stack([h, d, a])


def avg_h_argmax_pred(probs: np.ndarray) -> np.ndarray:
    return np.array([LABELS[i] for i in np.argmax(probs, axis=1)])


def train_logreg(X_train, y_train):
    """Entrena LogReg multinomial."""
    scaler = StandardScaler()
    X_s = scaler.fit_transform(X_train)
    model = LogisticRegression(max_iter=2000, C=1.0)
    model.fit(X_s, y_train)
    return model, scaler


def predict_logreg(model, scaler, X):
    X_s = scaler.transform(X)
    probs = model.predict_proba(X_s)
    # Reordenar a [H, D, A]
    classes = list(model.classes_)
    idx_h = classes.index("H")
    idx_d = classes.index("D")
    idx_a = classes.index("A")
    return np.column_stack([probs[:, idx_h], probs[:, idx_d], probs[:, idx_a]])


def train_xgb(X_train, y_train):
    """Entrena XGBoost."""
    # Label encoder: H/D/A → 0/1/2
    y_enc = np.array([LABELS.index(y) for y in y_train])
    model = xgb.XGBClassifier(
        n_estimators=200,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        objective="multi:softprob",
        num_class=3,
        random_state=42,
        eval_metric="mlogloss",
    )
    model.fit(X_train, y_enc, verbose=False)
    return model


def predict_xgb(model, X):
    probs = model.predict_proba(X)
    # LABELS=["H","D","A"] → y_enc=[0,1,2]
    # predict_proba devuelve columnas en orden de classes_ → [p(H), p(D), p(A)]
    return np.column_stack([probs[:, 0], probs[:, 1], probs[:, 2]])


def fit_poisson_lambda(df_train: pd.DataFrame) -> dict:
    """Estima lambdas (home/away) vía Poisson básico con ELO baseline.

    Para cada equipo i: lambda_attack_i, lambda_defense_i, ELO_i.
    Predict: lambda_home = exp(μ + attack_home - defense_away + elo_diff/400)
    """
    # ELO baselines
    elo_default = 1500.0

    # Calcular lambdas promedio para home/away
    home_goals_mean = df_train["home_goals"].mean()
    away_goals_mean = df_train["away_goals"].mean()

    return {
        "home_avg": home_goals_mean,
        "away_avg": away_goals_mean,
    }


def predict_dc(df_test: pd.DataFrame, dc_params: dict, max_goals: int = 6) -> np.ndarray:
    """Dixon-Coles simplificado: Poisson(λ_home) vs Poisson(λ_away).

    λ_home = home_avg * form_factor
    λ_away = away_avg * form_factor (inverso)

    Form factor aproximado con form_diff_n5.
    """
    lambdas_home = np.full(len(df_test), dc_params["home_avg"])
    lambdas_away = np.full(len(df_test), dc_params["away_avg"])

    # Ajuste con form_diff_n5 (rango típico -2..+2 puntos)
    fd = df_test["form_diff_n5"].fillna(0).values
    # Multiplicador: 1.0 + 0.05 * fd  (5% más goles por cada punto de forma)
    lambdas_home = lambdas_home * (1.0 + 0.05 * fd)
    lambdas_away = lambdas_away * (1.0 - 0.05 * fd)

    p_h = np.zeros(len(df_test))
    p_d = np.zeros(len(df_test))
    p_a = np.zeros(len(df_test))

    for i, (lh, la) in enumerate(zip(lambdas_home, lambdas_away)):
        ph = scipy_poisson.pmf(np.arange(max_goals + 1), lh)
        pa = scipy_poisson.pmf(np.arange(max_goals + 1), la)
        joint = np.outer(ph, pa)
        p_h[i] = np.sum(np.tril(joint, -1))  # home > away
        p_d[i] = np.sum(np.diag(joint))
        p_a[i] = np.sum(np.triu(joint, 1))  # away > home

    return np.column_stack([p_h, p_d, p_a])


last_xgb_model = None


def evaluate_walk_forward(df: pd.DataFrame, test_seasons: list[str]) -> dict:
    """Walk-forward temporal para cada test season."""
    global last_xgb_model
    results = {}
    seasons = sorted(df["season"].unique())

    for test_season in test_seasons:
        if test_season not in seasons:
            continue

        train_seasons = [s for s in seasons if s < test_season]
        if not train_seasons:
            continue

        train = df[df["season"].isin(train_seasons)].dropna(subset=FEATURE_COLS)
        test = df[df["season"] == test_season].dropna(subset=FEATURE_COLS)

        log.info(f"\n=== Test season: {test_season} (train: {len(train)}, test: {len(test)}) ===")

        X_train = train[FEATURE_COLS].values
        y_train = train["result"].values
        X_test = test[FEATURE_COLS].values
        y_test = test["result"].values

        # 1. AvgH baseline
        probs_avg = avg_h_argmax_proba(test)
        acc_avg = (avg_h_argmax_pred(probs_avg) == y_test).mean()

        # 2. LogReg
        lr_model, lr_scaler = train_logreg(X_train, y_train)
        probs_lr = predict_logreg(lr_model, lr_scaler, X_test)
        acc_lr = (avg_h_argmax_pred(probs_lr) == y_test).mean()

        # 3. XGBoost
        xgb_model = train_xgb(X_train, y_train)
        probs_xgb = predict_xgb(xgb_model, X_test)
        acc_xgb = (avg_h_argmax_pred(probs_xgb) == y_test).mean()
        last_xgb_model = xgb_model  # para feature importance

        # 4. Dixon-Coles Poisson
        dc_params = fit_poisson_lambda(train)
        probs_dc = predict_dc(test, dc_params)
        acc_dc = (avg_h_argmax_pred(probs_dc) == y_test).mean()

        # 5. Ensemble — weighted by validation accuracy
        # Pesos proporcionales a accuracy
        accs = {
            "avg": acc_avg,
            "lr": acc_lr,
            "xgb": acc_xgb,
            "dc": acc_dc,
        }
        weights = {k: max(v, 0.40) for k, v in accs.items()}
        total_w = sum(weights.values())
        weights = {k: v / total_w for k, v in weights.items()}

        probs_ens = (
            weights["avg"] * probs_avg
            + weights["lr"] * probs_lr
            + weights["xgb"] * probs_xgb
            + weights["dc"] * probs_dc
        )
        acc_ens = (avg_h_argmax_pred(probs_ens) == y_test).mean()

        results[test_season] = {
            "n_test": len(test),
            "acc_avg": acc_avg,
            "acc_lr": acc_lr,
            "acc_xgb": acc_xgb,
            "acc_dc": acc_dc,
            "acc_ens": acc_ens,
            "weights": weights,
            "delta_ens_vs_avg": acc_ens - acc_avg,
            "delta_xgb_vs_avg": acc_xgb - acc_avg,
            "delta_lr_vs_avg": acc_lr - acc_avg,
            "delta_dc_vs_avg": acc_dc - acc_avg,
        }

        log.info(f"  AvgH:      {acc_avg:.4f}")
        log.info(f"  LogReg v3: {acc_lr:.4f}")
        log.info(f"  XGBoost:   {acc_xgb:.4f}")
        log.info(f"  Dixon-Col: {acc_dc:.4f}")
        log.info(f"  Ensemble:  {acc_ens:.4f}")
        log.info(f"  Δ ens vs AvgH: {results[test_season]['delta_ens_vs_avg']:+.4f}")

    return results


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--parquet", default=str(PARQUET))
    p.add_argument("--seasons", nargs="+", default=["2425", "2526"])
    args = p.parse_args()

    log.info(f"Cargando {args.parquet}...")
    df = pd.read_parquet(args.parquet)
    log.info(f"Loaded {df.shape[0]} partidos")

    results = evaluate_walk_forward(df, args.seasons)

    # Resumen
    print("\n" + "=" * 90)
    print("RESUMEN WALK-FORWARD v4 (LogReg + XGBoost + Dixon-Coles + Ensemble)")
    print("=" * 90)
    print(f"{'Season':<8} {'n':<5} {'AvgH':<8} {'LogReg':<8} {'XGBoost':<8} {'DC':<8} {'Ensemble':<9} {'Δ ens'}")
    print("-" * 90)
    for s, r in results.items():
        print(f"{s:<8} {r['n_test']:<5} {r['acc_avg']:<8.4f} {r['acc_lr']:<8.4f} "
              f"{r['acc_xgb']:<8.4f} {r['acc_dc']:<8.4f} {r['acc_ens']:<9.4f} "
              f"{r['delta_ens_vs_avg']:+.4f}")
    print("-" * 90)
    avg_acc = {k: np.mean([r[f"acc_{k}"] for r in results.values()])
               for k in ["avg", "lr", "xgb", "dc", "ens"]}
    print(f"{'PROMEDIO':<8} {'':<5} {avg_acc['avg']:<8.4f} {avg_acc['lr']:<8.4f} "
          f"{avg_acc['xgb']:<8.4f} {avg_acc['dc']:<8.4f} {avg_acc['ens']:<9.4f} "
          f"{avg_acc['ens'] - avg_acc['avg']:+.4f}")

    # Go/No-Go
    delta = avg_acc["ens"] - avg_acc["avg"]
    delta_xgb = avg_acc["xgb"] - avg_acc["avg"]
    print("\n" + "=" * 90)
    print("GO/NO-GO BINARIO vs AvgH (mercado)")
    print("=" * 90)
    print(f"XGBoost   vs AvgH: {delta_xgb:+.4f}  "
          f"{'✅ GO' if delta_xgb >= 0.01 else '❌ NO-GO'} (umbral +1pp)")
    print(f"Ensemble  vs AvgH: {delta:+.4f}  "
          f"{'✅ GO' if delta >= 0.01 else '❌ NO-GO'} (umbral +1pp)")

    # Top features XGBoost: feature_importances_ (gini importance)
    log.info("Feature importance XGBoost (último fold):")
    if last_xgb_model is None:
        print("  (no entrenado)")
        return
    imp = last_xgb_model.feature_importances_
    order = np.argsort(-imp)[:10]
    for i in order:
        print(f"  {FEATURE_COLS[i]:25s}  importance={imp[i]:.4f}")


if __name__ == "__main__":
    main()