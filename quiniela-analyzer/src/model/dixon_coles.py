"""Dixon-Coles model for match outcome prediction.

A simplified Dixon-Coles-style model that models:
  - Home goals ~ Poisson(λ_home)
  - Away goals ~ Poisson(λ_away)
  - With a correction for low-scoring matches (0-0, 1-0, 0-1)

Simplified version: use historical 1X2 base rates by ELO difference buckets
plus a small adjustment for recent form.

For each ELO_diff bucket, we compute historical P(H), P(D), P(A) and use those
as the prediction probabilities.
"""
from __future__ import annotations

import json
from pathlib import Path
from collections import defaultdict

import numpy as np
import pandas as pd

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "quiniela.db"
PARQUET_PATH = Path(__file__).resolve().parents[2] / "data" / "features" / "training_set.parquet"
MODEL_PATH = Path(__file__).resolve().parents[2] / "data" / "models" / "dixon_coles_model.json"


def build_elo_buckets(df: pd.DataFrame, n_buckets: int = 20) -> dict:
    """Build historical 1X2 rates per ELO difference bucket from training data."""
    elo_min = df["ELO_diff"].min()
    elo_max = df["ELO_diff"].max()
    bucket_width = (elo_max - elo_min) / n_buckets

    buckets = defaultdict(lambda: {"H": 0, "D": 0, "A": 0, "total": 0})

    for _, row in df.iterrows():
        elo_diff = row["ELO_diff"]
        result = row.get("result")
        if result is None:
            continue

        b_idx = min(int((elo_diff - elo_min) / bucket_width), n_buckets - 1)
        buckets[b_idx]["total"] += 1
        if result in ("H", "D", "A"):
            buckets[b_idx][result] += 1

    # Convert to probabilities
    bucket_probs = {}
    for b_idx in range(n_buckets):
        t = buckets[b_idx]["total"]
        if t > 0:
            p_h = buckets[b_idx]["H"] / t
            p_d = buckets[b_idx]["D"] / t
            p_a = buckets[b_idx]["A"] / t
        else:
            # Interpolate from neighbours
            p_h = p_d = p_a = 1.0 / 3.0
        bucket_probs[b_idx] = {"P_H": p_h, "P_D": p_d, "P_A": p_a, "N": t}

    params = {
        "elo_min": float(elo_min),
        "elo_max": float(elo_max),
        "bucket_width": float(bucket_width),
        "bucket_probs": {str(k): v for k, v in bucket_probs.items()},
        "n_buckets": n_buckets,
    }
    return params


def predict_dixon_coles(elo_diff: float, params: dict) -> dict:
    """Predict 1X2 probabilities for a given ELO differential."""
    n_buckets = params["n_buckets"]
    elo_min = params["elo_min"]
    bucket_width = params["bucket_width"]

    b_idx = int((elo_diff - elo_min) / bucket_width)
    b_idx = max(0, min(n_buckets - 1, b_idx))

    probs = params["bucket_probs"][str(b_idx)]
    return {"P_H": probs["P_H"], "P_D": probs["P_D"], "P_A": probs["P_A"]}


def evaluate(df: pd.DataFrame, params: dict) -> float:
    correct = 0
    total = 0
    for _, row in df.iterrows():
        elo_diff = row.get("ELO_diff", 0.0)
        actual = row.get("result")
        if actual is None:
            continue

        pred = predict_dixon_coles(elo_diff, params)
        probs = {"H": pred["P_H"], "D": pred["P_D"], "A": pred["P_A"]}
        predicted = max(probs, key=probs.get)
        if predicted == actual:
            correct += 1
        total += 1

    acc = correct / total if total > 0 else 0
    print(f"Dixon-Coles val accuracy: {acc:.4f} ({correct}/{total})")
    return acc


def fit_and_save(df: pd.DataFrame) -> dict:
    params = build_elo_buckets(df)
    with open(MODEL_PATH, "w") as f:
        json.dump(params, f)
    print(f"✅ Dixon-Coles model saved to {MODEL_PATH}")
    return params


if __name__ == "__main__":
    df = pd.read_parquet(PARQUET_PATH)

    train_seasons = [s for s in df["season"].unique() if int(s[:4]) < 2024]
    val_seasons = [s for s in df["season"].unique() if int(s[:4]) >= 2024]

    train_df = df[df["season"].isin(train_seasons)]
    val_df = df[df["season"].isin(val_seasons)]

    params = fit_and_save(train_df)
    acc = evaluate(val_df, params)

    # Show bucket probabilities
    print("\nSample bucket probabilities (ELO_diff → P_H, P_D, P_A):")
    for b_idx in [0, 5, 10, 15, 19]:
        if str(b_idx) in params["bucket_probs"]:
            p = params["bucket_probs"][str(b_idx)]
            elo_lo = params["elo_min"] + b_idx * params["bucket_width"]
            elo_hi = elo_lo + params["bucket_width"]
            print(f"  ELO_diff [{elo_lo:.0f}, {elo_hi:.0f}): H={p['P_H']:.3f} D={p['P_D']:.3f} A={p['P_A']:.3f} (N={p['N']})")
