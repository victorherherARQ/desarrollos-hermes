#!/usr/bin/env python3
"""Generar predicciones semanales de quiniela y enviar a Telegram.

Uso:
  python3 scripts/weekly_quiniela_predictions.py --dry-run   # test
  python3 scripts/weekly_quiniela_predictions.py            # produccion
"""
import sqlite3, json, pickle, pathlib, urllib.request, sys
from collections import defaultdict
import numpy as np

ROOT = pathlib.Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
MODEL_DIR = ROOT / "data/models"
CACHE = DATA_DIR / "raw/transfermarkt_seed.json"
DRY_RUN = "--dry-run" in sys.argv

# ── Config Telegram ────────────────────────────────────────────────────────
BOT_TOKEN = next(
    l.split("=", 1)[1].strip()
    for l in pathlib.Path.home().joinpath(".hermes/.env").read_text().splitlines()
    if l.startswith("TELEGRAM_BOT_TOKEN")
)
CHAT_ID = "299986762"
THRESHOLD = 0.45

# ── 1. Scrapear Transfermarkt ──────────────────────────────────────────────
sys.path.insert(0, str(ROOT))
from src.features.transfermarkt_parser import fetch_laliga_squads

print("[1/5] Scraping Transfermarkt...")
teams = None
try:
    teams = fetch_laliga_squads()
    cache_data = [
        {
            "team_id": t.team_id,
            "tm_name": t.tm_name,
            "squad_size": t.squad_size,
            "total_market_value_eur_m": t.total_market_value_eur_m,
            "avg_player_value_eur_m": t.avg_player_value_eur_m,
            "average_age": t.average_age,
            "foreign_players": t.foreign_players,
        }
        for t in teams
    ]
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(cache_data, ensure_ascii=False, indent=2))
    print(f"  ✓ {len(teams)} equipos → {CACHE}")
except Exception as e:
    print(f"  ⚠ Error scraping Transfermarkt: {e}")
    if CACHE.exists():
        cache_data = json.loads(CACHE.read_text())
        print(f"  → Usando cache existente ({len(cache_data)} equipos)")
    else:
        cache_data = []

# ── 2. Guardar en DB ────────────────────────────────────────────────────────
print("[2/5] Actualizando DB...")
conn = sqlite3.connect(DATA_DIR / "quiniela.db")
cur = conn.cursor()

for row in cache_data:
    cur.execute("""
        INSERT INTO team_features
            (team_id, source, squad_size, total_market_value_eur_m,
             avg_player_value_eur_m, average_age, foreign_players, season)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(team_id, season) DO UPDATE SET
            source=excluded.source,
            squad_size=excluded.squad_size,
            total_market_value_eur_m=excluded.total_market_value_eur_m,
            avg_player_value_eur_m=excluded.avg_player_value_eur_m,
            average_age=excluded.average_age,
            foreign_players=excluded.foreign_players
    """, (
        row["team_id"], "transfermarkt",
        row["squad_size"], row.get("total_market_value_eur_m"),
        row.get("avg_player_value_eur_m"), row.get("average_age"),
        row.get("foreign_players"), "2526"
    ))
conn.commit()
print(f"  ✓ market values actualizados")

# ── 3. Cargar modelos ────────────────────────────────────────────────────────
print("[3/5] Cargando modelos...")
with open(MODEL_DIR / "logreg_model.pkl", "rb") as f:
    model = pickle.load(f)
with open(MODEL_DIR / "logreg_scaler.pkl", "rb") as f:
    scaler = pickle.load(f)
print(f"  ✓ LogReg + Scaler cargados")

# ── 4. Buscar partidos proximos ─────────────────────────────────────────────
print("[4/5] Buscando jornadas pendientes...")
upcoming = conn.execute("""
    SELECT match_id, season, division, jornada, matchday_date,
           home_team, away_team, home_goals, away_goals
    FROM matches
    WHERE (home_goals IS NULL OR away_goals IS NULL)
      AND division = 'laliga'
    ORDER BY season DESC, matchday_date ASC
    LIMIT 30
""").fetchall()

if not upcoming:
    print("  No hay jornadas pendientes. Fin.")
    conn.close()
    sys.exit(0)

jornada_groups = defaultdict(list)
for row in upcoming:
    jornada_groups[(row[2], int(row[3]))].append(row)

print(f"  ✓ {len(upcoming)} partidos en {len(jornada_groups)} jornada(s)")

# ── 5. Generar predicciones y enviar ───────────────────────────────────────
from src.model.features_join import build_feature_row

# Obtener las columnas del modelo
sample_feat = build_feature_row(conn, upcoming[0])
FEAT_COLS = [
    c for c in sample_feat.keys()
    if c not in ["match_id","season","division","jornada","matchday_date",
                 "home_team","away_team","result","home_goals","away_goals"]
] if sample_feat else []

total_predictions = 0
total_bets = 0

for (division, jornada), matches in sorted(jornada_groups.items()):
    lines = [f"🏆 *{division.upper()} — Jornada {jornada}*\n"]

    for row in matches:
        match_id, season, division, jornada, matchday_date, home, away = row[:7]

        feat = build_feature_row(conn, row)
        feat = feat or {}

        feat_row = {c: feat.get(c, 0.0) for c in FEAT_COLS}
        X = np.array([[feat_row[c] for c in FEAT_COLS]])
        X_s = scaler.transform(X)
        probs = model.predict_proba(X_s)[0]
        cls = list(model.classes_)

        pH = probs[cls.index("H")] if "H" in cls else 0.0
        pD = probs[cls.index("D")] if "D" in cls else 0.0
        pA = probs[cls.index("A")] if "A" in cls else 0.0
        max_p = max(pH, pD, pA)

        if max_p >= THRESHOLD:
            if pH == max_p:
                sig, conf = "1", pH
            elif pD == max_p:
                sig, conf = "X", pD
            else:
                sig, conf = "2", pA
            bet = f"→ *{sig}* ({conf:.0%})"
            total_bets += 1
        else:
            sig, conf = "?", max_p
            bet = f"→ ? (sin confianza, max={max_p:.0%})"

        lines.append(f"{home} vs {away}  {bet}")
        total_predictions += 1

    msg = "\n".join(lines)

    print(f"\n  Jornada {jornada}:")
    print("  " + "\n  ".join(lines.split("\n")[1:]))

    if not DRY_RUN:
        payload = json.dumps({"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}).encode()
        try:
            req = urllib.request.Request(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                data=payload,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read())
                print(f"    Telegram: {'✓' if result.get('ok') else '✗ ' + str(result)}")
        except Exception as e:
            print(f"    ⚠ Telegram: {e}")
    else:
        print("  [DRY RUN — no se envia]")

conn.close()
print(f"\n✅ Fin. {total_predictions} partidos, {total_bets} con apuesta activa (conf ≥ {THRESHOLD:.0%}).")
