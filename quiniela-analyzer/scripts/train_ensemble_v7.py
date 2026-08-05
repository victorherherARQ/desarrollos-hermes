"""v7: LogReg con AvgH PROBS como features (no argmax).

Hipótesis: el mercado da probabilidad implícita por resultado. Usar
P(avgH), P(avgD), P(avgA) como features + las otras 49 features.
El LogReg aprende la calibración óptima del mercado + correcciones.

vs v6: el mismo modelo pero con avg_h/d/a como input, no como única salida.

Walk-forward en 6 temporadas (2021 a 2526) para mayor robustez.
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
PARQUET = ROOT / "data" / "training_set_v7.parquet"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)


FEATURE_COLS_V7 = [
    # AvgH PROBS (3)
    "mkt_p_H", "mkt_p_D", "mkt_p_A",
    # Pinnacle sharp probs (3)
    "psc_p_H", "psc_p_D", "psc_p_A",
    # Odds originales (sigue siendo útil)
    "avg_h", "avg_d", "avg_a", "psc_h", "psc_d", "psc_a",
    # Form n=5
    "home_n5_w", "home_n5_d", "home_n5_l",
    "away_n5_w", "away_n5_d", "away_n5_l",
    # Form n=10
    "home_n10_wins", "home_n10_points_avg",
    "away_n10_wins", "away_n10_points_avg",
    # Form streaks/diffs
    "home_win_streak", "away_unbeaten_streak",
    "form_diff_n5", "form_diff_n10",
    # H2H
    "h2h5_home_wins", "h2h5_draws", "h2h5_away_wins",
    "h2h10_home_wins", "h2h10_draws", "h2h10_away_wins",
    # Rest
    "rest_days_home", "rest_days_away", "rest_days_diff",
    # xG_REAL StatsBomb + proxy fallback
    "home_xg_real_n5", "away_xg_real_n5", "xg_real_diff_n5",
    "home_xg_real_n10", "away_xg_real_n10", "xg_real_diff_n10",
    # ELO
    "elo_home", "elo_away", "elo_diff",
    # INTERACCIONES (NUEVO v7)
    "form_diff_x_mkt",  # form_diff_n10 × P(H)
    "xg_diff_x_mkt",    # xg_real_diff_n10 × P(H)
    "elo_diff_x_mkt",   # elo_diff × P(H)
]

LABELS = ["H", "D", "A"]


def avg_h_argmax_proba(df):
    h = 1.0 / df["avg_h"].values
    d = 1.0 / df["avg_d"].values
    a = 1.0 / df["avg_a"].values
    s = h + d + a
    return np.column_stack([h / s, d / s, a / s])


def avg_h_argmax_pred(probs):
    return np.array([LABELS[i] for i in np.argmax(probs, axis=1)])


def build_training_set_v7():
    """Carga base v6 + añade probs normalizadas + features interacción."""
    import sqlite3
    conn = sqlite3.connect(ROOT / "data" / "quiniela.db")
    df = pd.read_sql_query("""
        SELECT m.match_id, m.season, m.division, m.jornada, m.matchday_date,
               m.home_team, m.away_team, m.home_goals, m.away_goals, m.result
        FROM matches m WHERE m.result IS NOT NULL
    """, conn)
    df = df.merge(pd.read_sql_query(
        "SELECT match_id, imp_h, imp_d, imp_a, avg_h, avg_d, avg_a, psc_h, psc_d, psc_a FROM match_odds", conn),
        on="match_id", how="left")

    # Calcular probabilidades normalizadas (overround-out)
    df["mkt_p_H"] = (1.0 / df["avg_h"]) / (1/df["avg_h"] + 1/df["avg_d"] + 1/df["avg_a"])
    df["mkt_p_D"] = (1.0 / df["avg_d"]) / (1/df["avg_h"] + 1/df["avg_d"] + 1/df["avg_a"])
    df["mkt_p_A"] = (1.0 / df["avg_a"]) / (1/df["avg_h"] + 1/df["avg_d"] + 1/df["avg_a"])
    df["psc_p_H"] = (1.0 / df["psc_h"]) / (1/df["psc_h"] + 1/df["psc_d"] + 1/df["psc_a"])
    df["psc_p_D"] = (1.0 / df["psc_d"]) / (1/df["psc_h"] + 1/df["psc_d"] + 1/df["psc_a"])
    df["psc_p_A"] = (1.0 / df["psc_a"]) / (1/df["psc_h"] + 1/df["psc_d"] + 1/df["psc_a"])

    df = df.merge(pd.read_sql_query("""
        SELECT match_id,
               f5_wins_home AS home_n5_w, f5_draws_home AS home_n5_d,
               f5_losses_home AS home_n5_l,
               f5_wins_away AS away_n5_w, f5_draws_away AS away_n5_d,
               f5_losses_away AS away_n5_l,
               f10_wins_home AS home_n10_wins, f10_points_home AS home_n10_points_avg,
               f10_wins_away AS away_n10_wins, f10_points_away AS away_n10_points_avg,
               f5_win_streak_home AS home_win_streak,
               f5_unbeaten_streak_away AS away_unbeaten_streak,
               f5_points_diff AS form_diff_n5,
               f10_points_diff AS form_diff_n10
        FROM match_form
    """, conn), on="match_id", how="left")
    df = df.merge(pd.read_sql_query("""
        SELECT match_id,
               h2h5_wins_home AS h2h5_home_wins,
               h2h5_draws_home AS h2h5_draws,
               h2h5_losses_home AS h2h5_away_wins,
               h2h10_wins_home AS h2h10_home_wins,
               h2h10_draws_home AS h2h10_draws,
               h2h10_losses_home AS h2h10_away_wins
        FROM match_h2h
    """, conn), on="match_id", how="left")
    df = df.merge(pd.read_sql_query(
        "SELECT match_id, rest_days_home, rest_days_away, rest_days_diff FROM match_rest", conn),
        on="match_id", how="left")
    try:
        df = df.merge(pd.read_sql_query("""
            SELECT match_id,
                   home_xg_real_n5, away_xg_real_n5, xg_real_diff_n5,
                   home_xg_real_n10, away_xg_real_n10, xg_real_diff_n10
            FROM match_xg_real
        """, conn), on="match_id", how="left")
    except Exception as e:
        log.warning(f"match_xg_real no disponible: {e}")
    try:
        df = df.merge(pd.read_sql_query(
            "SELECT match_id, elo_home, elo_away, elo_diff FROM match_elo", conn),
            on="match_id", how="left")
    except Exception as e:
        log.warning(f"match_elo no disponible: {e}")

    # Interacciones (NUEVO v7)
    df["form_diff_x_mkt"] = df["form_diff_n10"] * df["mkt_p_H"]
    df["xg_diff_x_mkt"] = df["xg_real_diff_n10"] * df["mkt_p_H"]
    df["elo_diff_x_mkt"] = df["elo_diff"] * df["mkt_p_H"] / 100.0  # normalizar

    df = df.dropna(subset=["avg_h"])
    conn.close()
    return df


def train_logreg(X_train, y_train):
    scaler = StandardScaler()
    X_s = scaler.fit_transform(X_train)
    model = LogisticRegression(max_iter=2000, C=1.0)
    model.fit(X_s, y_train)
    return model, scaler


def predict_logreg(model, scaler, X):
    X_s = scaler.transform(X)
    probs = model.predict_proba(X_s)
    classes = list(model.classes_)
    return np.column_stack([probs[:, classes.index("H")],
                            probs[:, classes.index("D")],
                            probs[:, classes.index("A")]])


def train_xgb(X_train, y_train):
    y_enc = np.array([LABELS.index(y) for y in y_train])
    model = xgb.XGBClassifier(
        n_estimators=200, max_depth=4, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8,
        objective="multi:softprob", num_class=3,
        random_state=42, eval_metric="mlogloss",
    )
    model.fit(X_train, y_enc, verbose=False)
    return model


def predict_xgb(model, X):
    probs = model.predict_proba(X)
    return np.column_stack([probs[:, 0], probs[:, 1], probs[:, 2]])


def evaluate(df, test_seasons):
    results = {}
    seasons = sorted(df["season"].unique())
    for ts in test_seasons:
        if ts not in seasons:
            continue
        train_seasons = [s for s in seasons if s < ts]
        if not train_seasons:
            continue

        train = df[df["season"].isin(train_seasons)].dropna(subset=FEATURE_COLS_V7)
        test = df[df["season"] == ts].dropna(subset=FEATURE_COLS_V7)

        X_train = train[FEATURE_COLS_V7].values
        y_train = train["result"].values
        X_test = test[FEATURE_COLS_V7].values
        y_test = test["result"].values

        # AvgH argmax baseline
        probs_avg = avg_h_argmax_proba(test)
        acc_avg = (avg_h_argmax_pred(probs_avg) == y_test).mean()

        # LogReg v7
        lr, sc = train_logreg(X_train, y_train)
        probs_lr = predict_logreg(lr, sc, X_test)
        acc_lr = (avg_h_argmax_pred(probs_lr) == y_test).mean()

        # XGBoost v7
        xm = train_xgb(X_train, y_train)
        probs_xgb = predict_xgb(xm, X_test)
        acc_xgb = (avg_h_argmax_pred(probs_xgb) == y_test).mean()

        # Ensemble: 60% LogReg + 20% AvgH + 20% XGBoost (peso fijo, evita overfit)
        probs_ens = (
            0.60 * probs_lr
            + 0.20 * probs_avg
            + 0.20 * probs_xgb
        )
        acc_ens = (avg_h_argmax_pred(probs_ens) == y_test).mean()

        # Ensemble: LogReg + AvgH 50-50 (más conservador)
        probs_ens2 = 0.5 * probs_lr + 0.5 * probs_avg
        acc_ens2 = (avg_h_argmax_pred(probs_ens2) == y_test).mean()

        results[ts] = {
            "n_test": len(test),
            "acc_avg": acc_avg, "acc_lr": acc_lr, "acc_xgb": acc_xgb,
            "acc_ens3": acc_ens, "acc_ens2": acc_ens2,
            "delta_ens3_vs_avg": acc_ens - acc_avg,
            "delta_ens2_vs_avg": acc_ens2 - acc_avg,
            "delta_lr_vs_avg": acc_lr - acc_avg,
        }
        log.info(f"  ts={ts}: AvgH={acc_avg:.4f} LR={acc_lr:.4f} XGB={acc_xgb:.4f} "
                 f"Ens3={acc_ens:.4f} Ens2={acc_ens2:.4f}")
    return results


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--seasons", nargs="+", default=["2021", "2122", "2223", "2324", "2425", "2526"])
    p.add_argument("--save-parquet", action="store_true")
    args = p.parse_args()

    log.info("Construyendo training_set_v7...")
    df = build_training_set_v7()
    log.info(f"Loaded {df.shape[0]} partidos × {df.shape[1]} cols")
    log.info(f"Features: {len(FEATURE_COLS_V7)}")
    if args.save_parquet:
        df.to_parquet(PARQUET)
        log.info(f"Guardado en {PARQUET}")

    results = evaluate(df, args.seasons)

    print("\n" + "=" * 90)
    print("RESUMEN WALK-FORWARD v7 (AvgH probs + interacciones)")
    print("=" * 90)
    print(f"{'Season':<8} {'n':<5} {'AvgH':<7} {'LR':<7} {'XGB':<7} {'Ens3':<7} {'Ens2':<7} {'Δ LR':<7} {'Δ Ens2':<7}")
    print("-" * 90)
    for s, r in results.items():
        print(f"{s:<8} {r['n_test']:<5} {r['acc_avg']:<7.4f} {r['acc_lr']:<7.4f} "
              f"{r['acc_xgb']:<7.4f} {r['acc_ens3']:<7.4f} {r['acc_ens2']:<7.4f} "
              f"{r['delta_lr_vs_avg']:+.4f} {r['delta_ens2_vs_avg']:+.4f}")
    print("-" * 90)
    avg = {k: np.mean([r[f"acc_{k}"] for r in results.values()]) for k in ["avg", "lr", "xgb", "ens3", "ens2"]}
    print(f"{'AVG':<8} {'':<5} {avg['avg']:<7.4f} {avg['lr']:<7.4f} "
          f"{avg['xgb']:<7.4f} {avg['ens3']:<7.4f} {avg['ens2']:<7.4f} "
          f"{avg['lr']-avg['avg']:+.4f} {avg['ens2']-avg['avg']:+.4f}")

    print("\n" + "=" * 90)
    print("GO/NO-GO BINARIO v7 (vs AvgH, 6 temporadas)")
    print("=" * 90)
    for name, key in [("LogReg v7", "lr"), ("Ensemble3", "ens3"), ("Ensemble2 (LR+AvgH 50/50)", "ens2")]:
        delta = avg[key] - avg["avg"]
        print(f"{name:30s} vs AvgH: {delta:+.4f}  "
              f"{'✅ GO' if delta >= 0.01 else '❌ NO-GO'} (umbral +1pp)")


if __name__ == "__main__":
    main()