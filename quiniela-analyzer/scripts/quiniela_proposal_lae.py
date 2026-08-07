"""Genera propuesta de quiniela desde la lista OFICIAL de LAE."""
import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from team_name_map import normalize

DB_PATH = Path(__file__).parent.parent / "data" / "quiniela.db"


def load_lae_matches(date_str):
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute(
        """SELECT position, home_team, away_team, match_time
           FROM lae_quiniela WHERE match_date = ? ORDER BY position""",
        (date_str,),
    )
    matches = cur.fetchall()
    conn.close()
    return matches


def team_ppg(conn, lae_name, season="2526"):
    cur = conn.cursor()
    bd_name = normalize(lae_name)
    if not bd_name:
        return {"games": 0, "ppg": 0.0, "matched": "?"}
    cur.execute(
        """
        SELECT COUNT(*) AS games,
        AVG(CASE WHEN result = 'H' AND home_team = ? THEN 3
                 WHEN result = 'D' AND home_team = ? THEN 1
                 WHEN result = 'A' AND home_team = ? THEN 0
                 WHEN result = 'A' AND away_team = ? THEN 3
                 WHEN result = 'D' AND away_team = ? THEN 1
                 WHEN result = 'H' AND away_team = ? THEN 0
            END) AS ppg
        FROM matches
        WHERE (home_team = ? OR away_team = ?)
        AND season = ?
        """,
        (bd_name, bd_name, bd_name, bd_name, bd_name, bd_name,
         bd_name, bd_name, season),
    )
    row = cur.fetchone()
    return {
        "games": row[0] or 0, "ppg": row[1] or 0.0,
        "matched": bd_name,
    }


def predict_1x2(home_ppg, away_ppg, home_games, away_games):
    if home_games == 0 and away_games == 0:
        return "1", 0.45, 0.30, 0.25
    if home_games == 0:
        return "2", 0.30, 0.30, 0.40
    if away_games == 0:
        return "1", 0.45, 0.30, 0.25
    diff = home_ppg - away_ppg
    if diff > 0.3:
        return "1", 0.55, 0.25, 0.20
    elif diff < -0.3:
        return "2", 0.20, 0.25, 0.55
    else:
        return "X", 0.35, 0.35, 0.30


def save_proposals(jornada, season, matches, predictions):
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM quiniela_proposals WHERE jornada=? AND season=?",
        (jornada, season),
    )
    for i, (pos, home, away, time) in enumerate(matches):
        pred, prob_h, prob_d, prob_a = predictions[i]
        avg_h = round(1 / prob_h, 2) if prob_h > 0 else 99.9
        avg_d = round(1 / prob_d, 2) if prob_d > 0 else 99.9
        avg_a = round(1 / prob_a, 2) if prob_a > 0 else 99.9
        match_id = 200000 + pos
        cur.execute(
            """INSERT INTO quiniela_proposals
            (jornada, season, match_id, match_date, home_team, away_team,
             prediction, prediction_digit, odds_avg_h, odds_avg_d, odds_avg_a,
             prob_h, prob_d, prob_a, generated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
            (jornada, season, match_id, time, home, away,
             pred, pred, avg_h, avg_d, avg_a, prob_h, prob_d, prob_a),
        )
    conn.commit()
    conn.close()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--jornada", required=True, help="YYYY-MM-DD")
    p.add_argument("--jornada-num", type=int, default=1)
    p.add_argument("--season", default="2627")
    args = p.parse_args()

    matches = load_lae_matches(args.jornada)
    if not matches:
        print(f"No hay partidos LAE para {args.jornada}")
        return 1

    print(f"Generando propuesta J{args.jornada_num} {args.season} ({args.jornada}) "
          f"con {len(matches)} partidos oficiales")

    conn = sqlite3.connect(str(DB_PATH))
    predictions = []
    for pos, home, away, time in matches:
        h_stats = team_ppg(conn, home)
        a_stats = team_ppg(conn, away)
        pred, prob_h, prob_d, prob_a = predict_1x2(
            h_stats["ppg"], a_stats["ppg"],
            h_stats["games"], a_stats["games"],
        )
        predictions.append((pred, prob_h, prob_d, prob_a))
        print(f"  {pos:2}. {home:25} vs {away:25} | "
              f"h_ppg={h_stats['ppg']:.2f}({h_stats['games']}={h_stats['matched']}) "
              f"a_ppg={a_stats['ppg']:.2f}({a_stats['games']}={a_stats['matched']}) "
              f"→ {pred} ({prob_h:.0%}/{prob_d:.0%}/{prob_a:.0%})")

    conn.close()

    save_proposals(args.jornada_num, args.season, matches, predictions)
    print(f"\n[OK] Propuesta J{args.jornada_num} {args.season} guardada en BD")
    return 0


if __name__ == "__main__":
    sys.exit(main())
