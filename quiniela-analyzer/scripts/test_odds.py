import sqlite3, numpy as np

conn = sqlite3.connect("data/quiniela.db")
rows = conn.execute("""
    SELECT mo.imp_c_h, mo.imp_c_d, mo.imp_c_a,
           mo.imp_h, mo.imp_d, mo.imp_a,
           m.home_goals, m.away_goals, m.season
    FROM match_odds mo
    JOIN matches m ON mo.match_id = m.match_id
    WHERE mo.imp_h IS NOT NULL
    ORDER BY m.season, m.matchday_date
""").fetchall()
conn.close()

ich = np.array([r[0] for r in rows])
icd = np.array([r[1] for r in rows])
ica = np.array([r[2] for r in rows])
ih  = np.array([r[3] for r in rows])
id_ = np.array([r[4] for r in rows])
ia  = np.array([r[5] for r in rows])
hg  = np.array([r[6] for r in rows])
ag  = np.array([r[7] for r in rows])
y   = np.where(hg>ag, 1, np.where(hg<ag, 0, 2))
seasons = np.array([r[8] for r in rows])
val_mask = seasons >= '2425'

for name, ph, pd, pa in [("Closing imp", ich, icd, ica), ("Opening imp", ih, id_, ia)]:
    preds = np.argmax(np.vstack([ph, pd, pa]), axis=0)
    acc = (preds[val_mask] == y[val_mask]).mean()
    print(f"{name}: overall acc = {acc:.4f}")
    for cls, label in enumerate(["Draw","Home","Away"]):
        m = (y == cls) & val_mask
        n = m.sum()
        if n > 0:
            ca = (preds[m] == y[m]).mean()
            print(f"  {label}: {ca:.4f} ({n} samples)")

print("\n=== Selective betting (closing odds) ===")
for t in [0.35, 0.40, 0.45, 0.50, 0.55]:
    maxp = np.maximum(np.maximum(ich, icd), ica)
    mask = maxp >= t
    mv = mask & val_mask
    n = mv.sum()
    if n > 0:
        preds = np.argmax(np.vstack([ich, icd, ica]), axis=0)
        acc = (preds[mv] == y[mv]).mean()
        n_correct = int(acc * n)
        print(f"  threshold {t}: acc={acc:.4f}, n={n}, correct={n_correct}")
