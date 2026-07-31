"""Name embedding: 25-dimensional vector per team.

Components:
- 4 dims: team name length buckets [0-5, 6-8, 9-12, 13+]
- 5 dims: keyword one-hot (Real, Athletic, Club, Deportivo, Union)
- 16 dims: hash TF-IDF simplified (character n-gram hashing)

The full 25-dim vector is stored as a blob in the teams table
or as a separate lookup table.
"""
from __future__ import annotations

import hashlib
import sqlite3
import json
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "quiniela.db"

VECTOR_DIM = 25

# Keyword flags (one-hot, dims 4-8)
KEYWORDS = ["real", "athletic", "club", "deportivo", "union"]
KEYWORD_OFFSET = 4  # first 4 dims are length buckets


def _length_bucket(name: str) -> int:
    """Return bucket index 0-3 for name length."""
    n = len(name)
    if n <= 5:
        return 0
    elif n <= 8:
        return 1
    elif n <= 12:
        return 2
    else:
        return 3


def _keyword_flags(name: str) -> list[int]:
    """Return 5-dim one-hot for keyword presence."""
    name_lower = name.lower()
    return [1 if kw in name_lower else 0 for kw in KEYWORDS]


def _hash_tfidf(name: str, n: int = 16) -> list[float]:
    """16-dim hash TF-IDF simplified: character 2-grams hashed to buckets.

    Uses a deterministic hash and assigns 1.0 to the bucket if the n-gram
    hashes to it. Value is frequency-weighted.
    """
    ngrams = []
    name_lower = name.lower()
    for k in [2, 3]:
        for i in range(len(name_lower) - k + 1):
            ngrams.append(name_lower[i : i + k])

    # Count frequencies
    freq: dict[str, int] = {}
    for ng in ngrams:
        freq[ng] = freq.get(ng, 0) + 1

    # TF: term frequency normalized
    max_freq = max(freq.values()) if freq else 1
    tf = {ng: count / max_freq for ng, count in freq.items()}

    # IDF-like: we don't have corpus, so use 1.0 for all
    buckets = [0.0] * n
    for ng, weight in tf.items():
        h = int(hashlib.md5(ng.encode()).hexdigest(), 16)
        bucket = h % n
        buckets[bucket] = max(buckets[bucket], weight)

    return buckets


def compute_name_embedding(name: str) -> list[float]:
    """Compute 25-dim embedding for a team name."""
    vec = [0.0] * VECTOR_DIM

    # 4 length bucket dims
    lb = _length_bucket(name)
    vec[lb] = 1.0

    # 5 keyword dims
    kf = _keyword_flags(name)
    for i, v in enumerate(kf):
        vec[KEYWORD_OFFSET + i] = float(v)

    # 16 hash TF-IDF dims
    hf = _hash_tfidf(name)
    for i, v in enumerate(hf):
        vec[KEYWORD_OFFSET + len(KEYWORDS) + i] = v

    return vec


def init_name_embeddings(conn: sqlite3.Connection) -> None:
    """Add name_embedding column to teams if not exists."""
    try:
        conn.execute("ALTER TABLE teams ADD COLUMN name_embedding TEXT")
    except sqlite3.OperationalError:
        pass  # column already exists
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_teams_embedding ON teams(team_id)"
    )


def compute_and_store_all_embeddings(conn: sqlite3.Connection) -> int:
    """Compute and store embeddings for all teams in the teams table."""
    rows = conn.execute("SELECT team_id, name FROM teams").fetchall()
    updated = 0
    for team_id, name in rows:
        vec = compute_name_embedding(name or team_id)
        vec_json = json.dumps(vec)
        conn.execute(
            "UPDATE teams SET name_embedding = ? WHERE team_id = ?",
            (vec_json, team_id),
        )
        updated += 1
    return updated


def get_embedding(conn: sqlite3.Connection, team_id: str) -> Optional[list[float]]:
    """Get the stored embedding for a team, or compute on the fly."""
    row = conn.execute(
        "SELECT name_embedding FROM teams WHERE team_id = ?",
        (team_id,),
    ).fetchone()
    if row and row[0]:
        return json.loads(row[0])
    # Fallback: compute from teams table
    name_row = conn.execute("SELECT name FROM teams WHERE team_id = ?", (team_id,)).fetchone()
    if name_row:
        return compute_name_embedding(name_row[0])
    return None


def build_embeddings_table(conn: sqlite3.Connection) -> None:
    """Create or replace name_embeddings table."""
    conn.execute("DROP TABLE IF EXISTS name_embeddings")
    conn.execute(f"""
        CREATE TABLE name_embeddings (
            team_id TEXT PRIMARY KEY,
            embedding_json TEXT NOT NULL
        )
    """)
    rows = conn.execute("SELECT team_id, name FROM teams").fetchall()
    for team_id, name in rows:
        vec = compute_name_embedding(name or team_id)
        conn.execute(
            "INSERT INTO name_embeddings VALUES (?, ?)",
            (team_id, json.dumps(vec)),
        )


if __name__ == "__main__":
    conn = sqlite3.connect(DB_PATH)
    init_name_embeddings(conn)
    n = compute_and_store_all_embeddings(conn)
    conn.commit()
    print(f"✅ Computed and stored embeddings for {n} teams")

    # Verify
    sample = conn.execute("SELECT team_id, name, name_embedding FROM teams LIMIT 5").fetchall()
    for team_id, name, emb in sample:
        vec = json.loads(emb) if emb else []
        print(f"  {team_id} ({name}): {len(vec)} dims, first 5={vec[:5]}")
    conn.close()
