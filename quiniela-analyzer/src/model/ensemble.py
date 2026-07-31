"""Ensemble model: weighted vote of [ELO, Poisson, Dixon-Coles, LogisticRegression].

For each match, we collect probability predictions from each model and
combine them with weights proportional to their validation accuracy.
"""
from __future__ import annotations

import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "quiniela.db"
PARQUET_PATH = Path(__file__).resolve().parents[2] / "data" / "features" / "training_set.parquet"
MODEL_DIR = Path(__file__).resolve().parents[2] / "data" / "models"

# Individual model accuracies (from val set)
MODEL_ACCURACIES = {
    "logreg": 0.4622,
    "poisson": 0.4539,
    "dixon_coles": 0.4537,
    "elo": 0.4611,   # ELO puro (heuristic baseline)
}

BASELINE = 0.4688

# Weights proportional to accuracy (no baseline subtraction)
# Add small floor so no model gets 0 weight
RAW_WEIGHTS = {k: max(v, 0.40) for k, v in MODEL_ACCURACIES.items()}
total = sum(RAW_WEIGHTS.values())
WEIGHTS = {k: v / total for k, v in RAW_WEIGHTS.items()}

# Fixed ELO weight used directly (not via WEIGHTS dict)
ELO_WEIGHT = 0.15


def load_models():
    """Load all sub-models."""
    models = {}

    logreg_path = MODEL_DIR / "logreg_model.pkl"
    scaler_path = MODEL_DIR / "logreg_scaler.pkl"
    if logreg_path.exists() and scaler_path.exists():
        with open(logreg_path, "rb") as f:
            models["logreg"] = pickle.load(f)
        with open(scaler_path, "rb") as f:
            models["scaler"] = pickle.load(f)

    poisson_path = MODEL_DIR / "poisson_model.json"
    if poisson_path.exists():
        with open(poisson_path) as f:
            models["poisson"] = json.load(f)

    dixon_path = MODEL_DIR / "dixon_coles_model.json"
    if dixon_path.exists():
        with open(dixon_path) as f:
            models["dixon_coles"] = json.load(f)

    return models


def predict_logreg(models: dict, row: pd.Series) -> dict[str, float]:
    """Predict 1X2 probabilities from LogisticRegression."""
    from .logreg_baseline import FEATURE_COLS

    logreg = models["logreg"]
    scaler = models["scaler"]

    feat_vals = []
    for col in FEATURE_COLS:
        val = row.get(col, 0.0)
        if val is None:
            val = 0.0
        feat_vals.append(float(val))

    X = np.array(feat_vals).reshape(1, -1)
    X_s = scaler.transform(X)

    probs = logreg.predict_proba(X_s)[0]
    classes = logreg.classes_

    return {classes[i]: float(probs[i]) for i in range(len(classes))}


def predict_poisson(models: dict, elo_home: float, elo_away: float) -> dict[str, float]:
    """Predict 1X2 from Poisson model."""
    import math
    from scipy.stats import poisson as scipy_poisson

    p = models["poisson"]
    lambda_home = math.exp(p["a_home"] + p["b_home"] * elo_home / 1000.0)
    lambda_away = math.exp(p["a_away"] + p["b_away"] * elo_away / 1000.0)

    max_goals = 10
    p_home_win = 0.0
    p_draw = 0.0
    for g_home in range(max_goals + 1):
        for g_away in range(max_goals + 1):
            p_g_h = scipy_poisson.pmf(g_home, lambda_home)
            p_g_a = scipy_poisson.pmf(g_away, lambda_away)
            if g_home > g_away:
                p_home_win += p_g_h * p_g_a
            elif g_home == g_away:
                p_draw += p_g_h * p_g_a
    p_away_win = 1.0 - p_home_win - p_draw

    return {"H": p_home_win, "D": p_draw, "A": p_away_win}


def predict_dixon_coles(models: dict, elo_diff: float) -> dict[str, float]:
    """Predict 1X2 from Dixon-Coles bucket model."""
    p = models["dixon_coles"]
    n_buckets = p["n_buckets"]
    elo_min = p["elo_min"]
    bucket_width = p["bucket_width"]

    b_idx = int((elo_diff - elo_min) / bucket_width)
    b_idx = max(0, min(n_buckets - 1, b_idx))

    probs = p["bucket_probs"][str(b_idx)]
    return {"H": probs["P_H"], "D": probs["P_D"], "A": probs["P_A"]}


def predict_elo_simple(elo_home: float, elo_away: float) -> dict[str, float]:
    """Simple ELO-based prediction using expected score formula."""
    def expected(r_a, r_b):
        return 1.0 / (1.0 + 10.0 ** ((r_b - r_a) / 400.0))

    e_home = expected(elo_home + 80, elo_away)
    e_away = 1.0 - e_home

    p_d = 1.0 - e_home - e_away
    p_d = max(0.05, min(0.40, p_d))
    p_home = e_home - p_d / 2
    p_away = e_away - p_d / 2
    p_home = max(0.05, min(0.85, p_home))
    p_away = max(0.05, min(0.85, p_away))
    total = p_home + p_d + p_away
    return {"H": p_home / total, "D": p_d / total, "A": p_away / total}


def predict_ensemble(models: dict, row: pd.Series) -> dict[str, float]:
    """Combine predictions from all models with accuracy-proportional weights."""
    combined = {"H": 0.0, "D": 0.0, "A": 0.0}

    # ELO — hardcoded weight
    elo_h = float(row.get("ELO_home", 1500.0) or 1500.0)
    elo_a = float(row.get("ELO_away", 1500.0) or 1500.0)
    elo_probs = predict_elo_simple(elo_h, elo_a)
    for k in combined:
        combined[k] += ELO_WEIGHT * elo_probs[k]

    # Poisson
    if "poisson" in models:
        p = predict_poisson(models, elo_h, elo_a)
        w = WEIGHTS.get("poisson", 0.0)
        for k in combined:
            combined[k] += w * p[k]

    # Dixon-Coles
    if "dixon_coles" in models:
        elo_diff = float(row.get("ELO_diff", 0.0) or 0.0)
        p = predict_dixon_coles(models, elo_diff)
        w = WEIGHTS.get("dixon_coles", 0.0)
        for k in combined:
            combined[k] += w * p[k]

    # LogReg
    if "logreg" in models and "scaler" in models:
        try:
            p = predict_logreg(models, row)
            w = WEIGHTS.get("logreg", 0.0)
            for k in combined:
                combined[k] += w * p[k]
        except Exception:
            pass

    # Normalize
    total_p = sum(combined.values())
    if total_p > 0:
        combined = {k: v / total_p for k, v in combined.items()}

    return combined


def evaluate_ensemble(df: pd.DataFrame, models: dict) -> float:
    """Evaluate ensemble on a DataFrame."""
    correct = 0
    total = 0
    for _, row in df.iterrows():
        actual = row.get("result")
        if actual is None:
            continue

        probs = predict_ensemble(models, row)
        predicted = max(probs, key=probs.get)

        if predicted == actual:
            correct += 1
        total += 1

    acc = correct / total if total > 0 else 0
    return acc


def run_evaluation():
    print(f"Weights: {WEIGHTS}, ELO_WEIGHT={ELO_WEIGHT}")

    df = pd.read_parquet(PARQUET_PATH)

    train_seasons = [s for s in df["season"].unique() if int(s[:4]) < 2024]
    val_seasons = [s for s in df["season"].unique() if int(s[:4]) >= 2024]
    val_df = df[df["season"].isin(val_seasons)]

    models = load_models()
    print(f"Loaded models: {list(models.keys())}")

    acc = evaluate_ensemble(val_df, models)
    print(f"\nEnsemble val accuracy: {acc:.4f}")
    print(f"Baseline (always_1):   {BASELINE:.4f}")
    print(f"Best individual:       {max(MODEL_ACCURACIES.values()):.4f}")
    print(f"Improvement over baseline: {(acc - BASELINE)*100:+.2f} pp")

    return acc


if __name__ == "__main__":
    run_evaluation()
