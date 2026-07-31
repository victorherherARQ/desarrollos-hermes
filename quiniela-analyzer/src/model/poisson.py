"""Poisson model for match outcome prediction.

Estimates λ_home and λ_away using ELO ratings as attacking strength proxy.
P(H) = 1 - Φ((λ_away - λ_home) / sqrt(λ_home + λ_away))
where Φ is the CDF of the difference of two independent Poissons.
Actually: use a simpler approach:
  log(λ_home) = base + attack_home - defense_away + elo_home_adj
  log(λ_away) = base + attack_away - defense_home + elo_away_adj

We fit this on historical data using statsmodels or scipy, or use a simplified version.
For now: simplified ELO-based Poisson where ELO differential maps to goal expectation.
"""
from __future__ import annotations

import sqlite3
import json
from pathlib import Path
from collections import defaultdict

import numpy as np
import pandas as pd
from scipy.stats import poisson

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "quiniela.db"
PARQUET_PATH = Path(__file__).resolve().parents[2] / "data" / "features" / "training_set.parquet"
MODEL_PATH = Path(__file__).resolve().parents[2] / "data" / "models" / "poisson_model.json"


def estimate_poisson_params(df: pd.DataFrame) -> dict:
    """Estimate Poisson parameters from ELO differential.

    λ_home = exp(base + elo_factor * ELO_home)
    λ_away = exp(base + elo_factor * ELO_away)
    where elo_factor is learned from historical data.
    """
    # Simple OLS to estimate the mapping from ELO to average goals
    from scipy.optimize import minimize

    # observed goals per ELO bucket
    elo_bins = np.linspace(1300, 2000, 21)
    elo_center = (elo_bins[:-1] + elo_bins[1:]) / 2

    home_goals_by_elo = defaultdict(list)
    away_goals_by_elo = defaultdict(list)

    for _, row in df.iterrows():
        elo_h = row["ELO_home"]
        elo_a = row["ELO_away"]
        hg = row.get("home_goals")
        ag = row.get("away_goals")
        if hg is None or ag is None:
            continue
        # Bin by home ELO
        for i in range(len(elo_bins) - 1):
            if elo_bins[i] <= elo_h < elo_bins[i + 1]:
                home_goals_by_elo[i].append(hg)
                break
        for i in range(len(elo_bins) - 1):
            if elo_bins[i] <= elo_a < elo_bins[i + 1]:
                away_goals_by_elo[i].append(ag)
                break

    # Average goals per ELO bucket
    avg_home = []
    avg_away = []
    for i in range(len(elo_bins) - 1):
        avg_home.append(np.mean(home_goals_by_elo.get(i, [1.5])))
        avg_away.append(np.mean(away_goals_by_elo.get(i, [1.2])))

    # Fit exponential: avg_goals = exp(a + b * elo)
    # Use log-linear regression
    valid_h = [(elo_center[i], avg_home[i]) for i in range(len(elo_center)) if avg_home[i] > 0]
    valid_a = [(elo_center[i], avg_away[i]) for i in range(len(elo_center)) if avg_away[i] > 0]

    elo_h_arr = np.array([x[0] for x in valid_h])
    goals_h_arr = np.array([x[1] for x in valid_h])
    elo_a_arr = np.array([x[0] for x in valid_a])
    goals_a_arr = np.array([x[1] for x in valid_a])

    # log(goals) = a + b * elo/1000
    def fit_exp(elo_arr, goals_arr):
        x = elo_arr / 1000.0
        y = np.log(goals_arr)
        # least squares: y = a + b*x
        A = np.vstack([np.ones(len(x)), x]).T
        ATA = A.T @ A
        ATy = A.T @ y
        coeffs = np.linalg.solve(ATA, ATy)
        return coeffs[0], coeffs[1]

    a_h, b_h = fit_exp(elo_h_arr, goals_h_arr)
    a_a, b_a = fit_exp(elo_a_arr, goals_a_arr)

    # base goal rate at 1500 ELO
    base_home = np.exp(a_h + b_h * 1.5)
    base_away = np.exp(a_a + b_a * 1.5)

    params = {
        "a_home": a_h,
        "b_home": b_h,
        "a_away": a_a,
        "b_away": b_a,
        "base_home": base_home,
        "base_away": base_away,
    }

    print(f"Poisson params: base_home={base_home:.3f}, base_away={base_away:.3f}")
    print(f"  home: log(λ) = {a_h:.3f} + {b_h:.3f} * elo/1000")
    print(f"  away: log(λ) = {a_a:.3f} + {b_a:.3f} * elo/1000")

    return params


def predict_poisson(home_elo: float, away_elo: float, params: dict) -> dict:
    """Predict outcome probabilities using Poisson model.

    Returns dict with P(H), P(D), P(A) and expected goals.
    """
    import math

    lambda_home = math.exp(params["a_home"] + params["b_home"] * home_elo / 1000.0)
    lambda_away = math.exp(params["a_away"] + params["b_away"] * away_elo / 1000.0)

    # Compute P(1X2) via Poisson PMF convolution
    max_goals = 10
    p_home_win = 0.0
    p_draw = 0.0
    for g_home in range(max_goals + 1):
        for g_away in range(max_goals + 1):
            p_g_h = poisson.pmf(g_home, lambda_home)
            p_g_a = poisson.pmf(g_away, lambda_away)
            if g_home > g_away:
                p_home_win += p_g_h * p_g_a
            elif g_home == g_away:
                p_draw += p_g_h * p_g_a
    p_away_win = 1.0 - p_home_win - p_draw

    return {
        "lambda_home": lambda_home,
        "lambda_away": lambda_away,
        "P_H": p_home_win,
        "P_D": p_draw,
        "P_A": p_away_win,
    }


def fit_and_save(df: pd.DataFrame) -> dict:
    params = estimate_poisson_params(df)
    with open(MODEL_PATH, "w") as f:
        json.dump(params, f)
    print(f"✅ Poisson model saved to {MODEL_PATH}")
    return params


def evaluate(df: pd.DataFrame, params: dict) -> float:
    """Evaluate Poisson model accuracy on a DataFrame."""
    correct = 0
    total = 0
    for _, row in df.iterrows():
        elo_h = row.get("ELO_home", 1500)
        elo_a = row.get("ELO_away", 1500)
        actual = row.get("result", None)
        if actual is None:
            continue

        pred = predict_poisson(elo_h, elo_a, params)
        probs = {"H": pred["P_H"], "D": pred["P_D"], "A": pred["P_A"]}
        predicted = max(probs, key=probs.get)

        if predicted == actual:
            correct += 1
        total += 1

    acc = correct / total if total > 0 else 0
    print(f"Poisson val accuracy: {acc:.4f} ({correct}/{total})")
    return acc


if __name__ == "__main__":
    df = pd.read_parquet(PARQUET_PATH)

    # Temporal split
    train_seasons = [s for s in df["season"].unique() if int(s[:4]) < 2024]
    val_seasons = [s for s in df["season"].unique() if int(s[:4]) >= 2024]

    train_df = df[df["season"].isin(train_seasons)]
    val_df = df[df["season"].isin(val_seasons)]

    params = fit_and_save(train_df)
    acc = evaluate(val_df, params)
