"""Ensemble v6: xG_REAL (StatsBomb) + ELO + odds + form + h2h + rest.

Features v6 (49 total):
  - 9 odds: imp_h/d/a, avg_h/d/a, psc_h/d/a
  - 16 form: home/away n5/n10
  - 6 h2h: h2h5/10 home/draw/away
  - 3 rest: rest_days_home/away/diff
  - 6 xG_real: home/away/diff n5/n10 (StatsBomb + proxy fallback)
  - 3 elo: elo_home/away/diff

Walk-forward temporal vs AvgH (mercado).
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
PARQUET = ROOT / "data" / "training_set_v6.parquet"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)


FEATURE_COLS_V6 = [
    # Odds
    "imp_h", "imp_d", "imp_a", "avg_h", "avg_d", "avg_a",
    "psc_h", "psc_d", "psc_a",
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
    # xG_REAL (StatsBomb + proxy fallback) — NUEVO v6
    "home_xg_real_n5", "away_xg_real_n5", "xg_real_diff_n5",
    "home_xg_real_n10", "away_xg_real_n10", "xg_real_diff_n10",
    # ELO dinámico
    "elo_home", "elo_away", "elo_diff",
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


def build_training_set_v6():
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

    # xG_REAL (NUEVO v6)
    try:
        df = df.merge(pd.read_sql_query("""
            SELECT match_id,
                   home_xg_real_n5, away_xg_real_n5, xg_real_diff_n5,
                   home_xg_real_n10, away_xg_real_n10, xg_real_diff_n10
            FROM match_xg_real
        """, conn), on="match_id", how="left")
    except Exception as e:
        log.warning(f"match_xg_real no disponible: {e}")

    # ELO dinámico
    try:
        df = df.merge(pd.read_sql_query(
            "SELECT match_id, elo_home, elo_away, elo_diff FROM match_elo", conn),
            on="match_id", how="left")
    except Exception as e:
        log.warning(f"match_elo no disponible: {e}")

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

        train = df[df["season"].isin(train_seasons)].dropna(subset=FEATURE_COLS_V6)
        test = df[df["season"] == ts].dropna(subset=FEATURE_COLS_V6)

        X_train = train[FEATURE_COLS_V6].values
        y_train = train["result"].values
        X_test = test[FEATURE_COLS_V6].values
        y_test = test["result"].values

        probs_avg = avg_h_argmax_proba(test)
        acc_avg = (avg_h_argmax_pred(probs_avg) == y_test).mean()

        lr, sc = train_logreg(X_train, y_train)
        probs_lr = predict_logreg(lr, sc, X_test)
        acc_lr = (avg_h_argmax_pred(probs_lr) == y_test).mean()

        xm = train_xgb(X_train, y_train)
        probs_xgb = predict_xgb(xm, X_test)
        acc_xgb = (avg_h_argmax_pred(probs_xgb) == y_test).mean()

        weights = {
            "avg": max(acc_avg, 0.40),
            "lr": max(acc_lr, 0.40),
            "xgb": max(acc_xgb, 0.40),
        }
        total = sum(weights.values())
        weights = {k: v / total for k, v in weights.items()}
        probs_ens = (
            weights["avg"] * probs_avg
            + weights["lr"] * probs_lr
            + weights["xgb"] * probs_xgb
        )
        acc_ens = (avg_h_argmax_pred(probs_ens) == y_test).mean()

        results[ts] = {
            "n_test": len(test),
            "acc_avg": acc_avg, "acc_lr": acc_lr, "acc_xgb": acc_xgb, "acc_ens": acc_ens,
            "delta_ens_vs_avg": acc_ens - acc_avg,
            "delta_xgb_vs_avg": acc_xgb - acc_avg,
            "delta_lr_vs_avg": acc_lr - acc_avg,
        }
        log.info(f"  ts={ts}: AvgH={acc_avg:.4f} LR={acc_lr:.4f} XGB={acc_xgb:.4f} Ens={acc_ens:.4f}")
    return results


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--seasons", nargs="+", default=["2425", "2526"])
    p.add_argument("--save-parquet", action="store_true")
    args = p.parse_args()

    log.info("Construyendo training_set_v6...")
    df = build_training_set_v6()
    log.info(f"Loaded {df.shape[0]} partidos × {df.shape[1]} cols")
    if args.save_parquet:
        df.to_parquet(PARQUET)
        log.info(f"Guardado en {PARQUET}")

    n_with_xg = df["home_xg_real_n5"].notna().sum()
    n_with_elo = df["elo_home"].notna().sum()
    log.info(f"Con xG_real: {n_with_xg} ({100*n_with_xg/len(df):.1f}%)")
    log.info(f"Con ELO: {n_with_elo} ({100*n_with_elo/len(df):.1f}%)")

    results = evaluate(df, args.seasons)

    print("\n" + "=" * 80)
    print("RESUMEN WALK-FORWARD v6 (con xG_REAL StatsBomb + ELO dinámico)")
    print("=" * 80)
    print(f"{'Season':<8} {'n':<5} {'AvgH':<8} {'LogReg':<8} {'XGBoost':<8} {'Ensemble':<9} {'Δ ens'}")
    print("-" * 80)
    for s, r in results.items():
        print(f"{s:<8} {r['n_test']:<5} {r['acc_avg']:<8.4f} {r['acc_lr']:<8.4f} "
              f"{r['acc_xgb']:<8.4f} {r['acc_ens']:<9.4f} {r['delta_ens_vs_avg']:+.4f}")
    print("-" * 80)
    avg = {k: np.mean([r[f"acc_{k}"] for r in results.values()]) for k in ["avg", "lr", "xgb", "ens"]}
    print(f"{'AVG':<8} {'':<5} {avg['avg']:<8.4f} {avg['lr']:<8.4f} "
          f"{avg['xgb']:<8.4f} {avg['ens']:<9.4f} {avg['ens']-avg['avg']:+.4f}")

    delta = avg["ens"] - avg["avg"]
    delta_xgb = avg["xgb"] - avg["avg"]
    print("\n" + "=" * 80)
    print("GO/NO-GO BINARIO v6 (vs AvgH)")
    print("=" * 80)
    print(f"XGBoost  vs AvgH: {delta_xgb:+.4f}  "
          f"{'✅ GO' if delta_xgb >= 0.01 else '❌ NO-GO'} (umbral +1pp)")
    print(f"Ensemble vs AvgH: {delta:+.4f}  "
          f"{'✅ GO' if delta >= 0.01 else '❌ NO-GO'} (umbral +1pp)")


if __name__ == "__main__":
    main()