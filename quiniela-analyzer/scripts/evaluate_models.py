"""Evaluate all models with different strategies."""
import pandas as pd, numpy as np, pickle, json, shutil
from pathlib import Path
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

MODEL_DIR = Path("data/models")

df = pd.read_parquet("data/features/training_set_v2.parquet")
val_seasons = [s for s in df["season"].unique() if int(s[:4]) >= 2024]
val_df = df[df["season"].isin(val_seasons)]
train_df = df[df["season"].isin([s for s in df["season"].unique() if int(s[:4]) < 2024])]

all_cols = [c for c in df.columns if c not in ["match_id","season","division","jornada","matchday_date","home_team","away_team","result","home_goals","away_goals"]]
X_tr = train_df[all_cols].fillna(0.0).values
y_tr = train_df["result"].values
X_vl = val_df[all_cols].fillna(0.0).values
y_vl = val_df["result"].values

BASELINE = 0.4688

# Baseline always_H
base_acc = (np.ones(len(y_vl)) == (y_vl == "H")).mean() * (y_vl == "H").mean() + (y_vl != "H").mean() * 0
base_acc = (y_vl == "H").mean()  # proportion of H in val
print(f"Baseline always_H (fraction H in val): {base_acc:.4f}")
print(f"Real distribution val: H={int((y_vl=='H').sum())} D={int((y_vl=='D').sum())} A={int((y_vl=='A').sum())}")

scaler = StandardScaler()
X_tr_s = scaler.fit_transform(X_tr)
X_vl_s = scaler.transform(X_vl)

# LogReg balanced
lr = LogisticRegression(max_iter=2000, solver="lbfgs", class_weight="balanced")
lr.fit(X_tr_s, y_tr)
cls = list(lr.classes_)
lr_H = lr.predict_proba(X_vl_s)[:, cls.index("H")]
lr_D = lr.predict_proba(X_vl_s)[:, cls.index("D")]
lr_A = lr.predict_proba(X_vl_s)[:, cls.index("A")]
lr_pred = np.array(["H","D","A"])[np.argmax(np.vstack([lr_H, lr_D, lr_A]), axis=0)]
lr_acc = (lr_pred == y_vl).mean()
print(f"\nBalanced LogReg: {lr_acc:.4f} ({(lr_acc-BASELINE)*100:+.2f}pp)")

# Breakdown
for s, lbl in [("H","Local"),("D","Empate"),("A","Visitante")]:
    m = y_vl == s
    correct = (lr_pred[m] == s).sum()
    print(f"  {s} {lbl}: n={m.sum()} ({m.mean()*100:.0f}%), acc={(correct/m.sum()):.3f} correct={correct}")

# Top-K confidence approach
print("\nTop-K: only bet when max probability > threshold")
for thresh in [0.35, 0.38, 0.40, 0.42, 0.45]:
    max_prob = np.maximum(np.maximum(lr_H, lr_D), lr_A)
    mask = max_prob >= thresh
    n = mask.sum()
    if n < 50:
        continue
    topk_pred = lr_pred[mask]
    topk_actual = y_vl[mask]
    topk_acc = (topk_pred == topk_actual).mean()
    base_topk = (topk_actual == "H").mean()
    print(f"  t={thresh}: n={n}, acc={topk_acc:.4f}, base_H={base_topk:.4f}, delta={(topk_acc-base_topk)*100:+.2f}pp")

# Value betting: bet on A when model disagrees with baseline
print("\nValue betting: bet A when P(A) >> baseline frequency")
real_pA = (y_tr == "A").mean()
real_pD = (y_tr == "D").mean()
print(f"Training frequencies: H={(y_tr=='H').mean():.3f} D={real_pD:.3f} A={real_pA:.3f}")

# Boost D and A relative to H using Platt scaling approach
# Instead of using raw probabilities, use log-odds relative to baseline
baseline_H = (y_tr == "H").mean()
baseline_D = (y_tr == "D").mean()
baseline_A = (y_tr == "A").mean()

# Log-odds under baseline
lo_H = np.log(baseline_H / (1 - baseline_H))
lo_D = np.log(baseline_D / (1 - baseline_D))
lo_A = np.log(baseline_A / (1 - baseline_A))

# Calibrated predictions: use Platt scaling
# Fit a logistic on the predictions
from sklearn.linear_model import LogisticRegression as LR2

# Simple approach: calibrate each class separately
def calibrate_class(y_binary, probs, y_all):
    """Calibrate probabilities for one class."""
    # Use isotonic regression-like approach
    # Compare predicted probability to actual frequency in bins
    bins = np.linspace(0, 1, 11)
    calibrated = np.zeros_like(probs)
    for i in range(len(bins)-1):
        mask = (probs >= bins[i]) & (probs < bins[i+1])
        if mask.sum() > 10:
            freq = (y_binary[mask]).mean()
            calibrated[mask] = freq
        else:
            calibrated[mask] = probs[mask]
    return calibrated

y_tr_H = (y_tr == "H").astype(float)
y_tr_D = (y_tr == "D").astype(float)
y_tr_A = (y_tr == "A").astype(float)

# Calibrate on training set predictions
lr_tr_H = lr.predict_proba(X_tr_s)[:, cls.index("H")]
lr_tr_D = lr.predict_proba(X_tr_s)[:, cls.index("D")]
lr_tr_A = lr.predict_proba(X_tr_s)[:, cls.index("A")]

# Simple: just rescale probabilities to match real frequencies
# Scale factor = real_freq / mean_predicted_freq
scale_H = baseline_H / lr_tr_H.mean()
scale_D = baseline_D / lr_tr_D.mean()
scale_A = baseline_A / lr_tr_A.mean()

cal_H = np.clip(lr_H * scale_H, 0.01, 0.99)
cal_D = np.clip(lr_D * scale_D, 0.01, 0.99)
cal_A = np.clip(lr_A * scale_A, 0.01, 0.99)
tot_cal = cal_H + cal_D + cal_A
cal_H /= tot_cal; cal_D /= tot_cal; cal_A /= tot_cal

cal_pred = np.array(["H","D","A"])[np.argmax(np.vstack([cal_H, cal_D, cal_A]), axis=0)]
cal_acc = (cal_pred == y_vl).mean()
print(f"\nCalibrated predictions: {cal_acc:.4f} ({(cal_acc-BASELINE)*100:+.2f}pp)")

for s, lbl in [("H","Local"),("D","Empate"),("A","Visitante")]:
    m = y_vl == s
    correct = (cal_pred[m] == s).sum()
    print(f"  {s} {lbl}: n={m.sum()}, acc={(correct/m.sum()):.3f}")

# Optimal threshold: pick sign with highest calibrated probability
print(f"\nBaseline always_H: {BASELINE:.4f}")
print(f"Best single-model accuracy: {max(lr_acc, cal_acc):.4f}")

# Save final models
with open(MODEL_DIR/"logreg_model.pkl", "wb") as f: pickle.dump(lr, f)
with open(MODEL_DIR/"logreg_scaler.pkl", "wb") as f: pickle.dump(scaler, f)
print("\nModels saved.")
