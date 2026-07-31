"""Logistic Regression baseline model for match outcome prediction.

Train: 2010-2023. Validation: 2024-2025.
Features: ELO_diff, stadium capacities, name embeddings, news scores.
Target: result (H/D/A) as multiclass.

Verify: accuracy > 46.88% (baseline always_1).
"""
from __future__ import annotations

import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score, classification_report

# ── paths ──────────────────────────────────────────────────────────────────
DB_PATH = Path(__file__).resolve().parents[2] / "data" / "quiniela.db"
PARQUET_PATH = Path(__file__).resolve().parents[2] / "data" / "features" / "training_set.parquet"
MODEL_PATH = Path(__file__).resolve().parents[2] / "data" / "models" / "logreg_model.pkl"
SCALER_PATH = Path(__file__).resolve().parents[2] / "data" / "models" / "logreg_scaler.pkl"
OUT_PATH = Path(__file__).resolve().parents[2] / "data" / "reports" / "logreg_results.json"

MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)

# ── feature columns ────────────────────────────────────────────────────────
FEATURE_COLS = [
    "ELO_diff",
    "ELO_home", "ELO_away",
    "stadium_capacity_home", "stadium_capacity_away",
    "news_score_home", "news_score_away",
]
# Add embedding cols
for prefix in ["emb_home_", "emb_away_"]:
    for i in range(25):
        FEATURE_COLS.append(f"{prefix}{i}")


def load_data() -> pd.DataFrame:
    if PARQUET_PATH.exists():
        return pd.read_parquet(PARQUET_PATH)
    # Fallback: build from DB
    from .features_join import build_training_set
    import sqlite3
    conn = sqlite3.connect(DB_PATH)
    return build_training_set(conn)


def train_val_split(df: pd.DataFrame):
    """Temporal split: train on seasons before 2024, validate on 2024-2025."""
    train_seasons = [s for s in df["season"].unique() if int(s[:4]) < 2024]
    val_seasons = [s for s in df["season"].unique() if int(s[:4]) >= 2024]

    train_df = df[df["season"].isin(train_seasons)]
    val_df = df[df["season"].isin(val_seasons)]

    print(f"Train: {len(train_df)} rows ({len(train_seasons)} seasons)")
    print(f"Val:   {len(val_df)} rows ({len(val_seasons)} seasons)")
    return train_df, val_df


def prepare_xy(df: pd.DataFrame):
    """Extract feature matrix X and label y from dataframe."""
    # Fill any NaN with 0
    X = df[FEATURE_COLS].fillna(0.0).values.astype(float)
    y = df["result"].values
    return X, y


def train_logreg(train_df: pd.DataFrame, val_df: pd.DataFrame):
    """Train LogisticRegression and evaluate on validation set."""
    X_train, y_train = prepare_xy(train_df)
    X_val, y_val = prepare_xy(val_df)

    # Scale features
    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_val_s = scaler.transform(X_val)

    # Train
    model = LogisticRegression(
        max_iter=1000,
        solver="lbfgs",
        C=1.0,
        random_state=42,
    )
    model.fit(X_train_s, y_train)

    # Predict
    y_pred_train = model.predict(X_train_s)
    y_pred_val = model.predict(X_val_s)

    acc_train = accuracy_score(y_train, y_pred_train)
    acc_val = accuracy_score(y_val, y_pred_val)

    print(f"\nTrain accuracy: {acc_train:.4f}")
    print(f"Val accuracy:   {acc_val:.4f}")
    print(f"Baseline (always_1): 0.4688")
    print(f"Improvement: {(acc_val - 0.4688)*100:+.2f} pp")

    print("\nClassification report (val):")
    print(classification_report(y_val, y_pred_val))

    # Per-season val accuracy
    per_season = {}
    for season in sorted(val_df["season"].unique()):
        mask = val_df["season"] == season
        X_s = scaler.transform(val_df.loc[mask, FEATURE_COLS].fillna(0.0).values.astype(float))
        y_s = val_df.loc[mask, "result"].values
        pred_s = model.predict(X_s)
        per_season[season] = round(accuracy_score(y_s, pred_s), 4)

    print("\nPer-season val accuracy:")
    for s, a in per_season.items():
        print(f"  {s}: {a:.4f}")

    # Save model + scaler
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(model, f)
    with open(SCALER_PATH, "wb") as f:
        pickle.dump(scaler, f)

    results = {
        "train_accuracy": round(acc_train, 4),
        "val_accuracy": round(acc_val, 4),
        "baseline": 0.4688,
        "per_season": per_season,
        "n_train": len(train_df),
        "n_val": len(val_df),
        "model_path": str(MODEL_PATH),
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\n✅ Model saved to {MODEL_PATH}")
    print(f"✅ Results saved to {OUT_PATH}")

    return model, scaler, results


if __name__ == "__main__":
    df = load_data()
    print(f"Loaded {len(df)} matches from parquet")
    print(f"Columns: {len(df.columns)} ({len(FEATURE_COLS)} features)")

    train_df, val_df = train_val_split(df)
    train_logreg(train_df, val_df)
