"""
UFC ELO Rating Engine

Dual-track ELO system: one unified cross-division rating and one per-weight-class.
K-factor adapts based on finish type, title fights, and round of finish.
"""

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

DB_PATH = Path(__file__).parent / "ufc_fights.db"
INITIAL_ELO = 1500.0
BASE_K = 32.0


# ── K-Factor Calculation ────────────────────────────────────────────────────

def classify_method(method: str) -> str:
    """Classify a method string into 'finish' or 'decision'."""
    method = method.upper()
    if method in ("KO/TKO", "SUB", "TKO", "KO"):
        return "finish"
    if method.startswith("KO") or method.startswith("TKO") or method.startswith("SUB"):
        return "finish"
    # DQ counts as a decision-weight outcome (less decisive)
    return "decision"


def calculate_k(method: str, is_title: bool, finish_round: int | None) -> float:
    """
    Adaptive K-factor:
      Base: 32
      × 1.5  for finishes (KO/TKO/SUB)
      × 1.25 for title fights
      × round multiplier for finishes: R1=1.3, R2=1.2, R3=1.1, R4=1.05, R5=1.0
    All multipliers stack multiplicatively.
    """
    k = BASE_K
    is_finish = classify_method(method) == "finish"

    if is_finish:
        k *= 1.5

    if is_title:
        k *= 1.25

    if is_finish and finish_round is not None:
        round_mult = max(1.0, 1.3 - 0.1 * (finish_round - 1))
        k *= round_mult

    return k


# ── ELO Math ────────────────────────────────────────────────────────────────

def expected_score(ra: float, rb: float) -> float:
    """Expected score for player A given ratings ra, rb."""
    return 1.0 / (1.0 + 10.0 ** ((rb - ra) / 400.0))


def update_ratings(ra: float, rb: float, score_a: float, k: float) -> tuple[float, float]:
    """Return (new_ra, new_rb) after a result. score_a: 1=A wins, 0=A loses, 0.5=draw."""
    ea = expected_score(ra, rb)
    new_ra = ra + k * (score_a - ea)
    new_rb = rb + k * ((1.0 - score_a) - (1.0 - ea))
    return new_ra, new_rb


# ── Prediction ──────────────────────────────────────────────────────────────

def predict(fighter_a: str, fighter_b: str, elo_type: str = "unified",
            db_path: str | Path = DB_PATH) -> dict:
    """
    Predict win probability for two fighters based on current ELO.

    Returns:
        {
            "fighter_a": {"name": str, "elo": float, "win_prob": float},
            "fighter_b": {"name": str, "elo": float, "win_prob": float},
            "elo_type": str,
        }
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    def get_elo(name: str) -> float | None:
        row = conn.execute(
            """SELECT ce.rating FROM current_elo ce
               JOIN fighters f ON f.id = ce.fighter_id
               WHERE f.name = ? AND ce.elo_type = ?""",
            (name, elo_type),
        ).fetchone()
        return row["rating"] if row else None

    ra = get_elo(fighter_a)
    rb = get_elo(fighter_b)
    conn.close()

    if ra is None:
        raise ValueError(f"Fighter not found: {fighter_a!r} (elo_type={elo_type!r})")
    if rb is None:
        raise ValueError(f"Fighter not found: {fighter_b!r} (elo_type={elo_type!r})")

    prob_a = expected_score(ra, rb)
    return {
        "fighter_a": {"name": fighter_a, "elo": round(ra, 1), "win_prob": round(prob_a, 4)},
        "fighter_b": {"name": fighter_b, "elo": round(rb, 1), "win_prob": round(1 - prob_a, 4)},
        "elo_type": elo_type,
    }


# ── Backfill Engine ─────────────────────────────────────────────────────────

ELO_TABLES_SCHEMA = """
CREATE TABLE IF NOT EXISTS elo_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fighter_id INTEGER NOT NULL REFERENCES fighters(id),
    fight_id INTEGER NOT NULL REFERENCES fights(id),
    elo_type TEXT NOT NULL,
    elo_before REAL NOT NULL,
    elo_after REAL NOT NULL,
    fight_date TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS current_elo (
    fighter_id INTEGER NOT NULL REFERENCES fighters(id),
    elo_type TEXT NOT NULL,
    rating REAL NOT NULL,
    fights_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (fighter_id, elo_type)
);

CREATE INDEX IF NOT EXISTS idx_elo_history_fighter ON elo_history(fighter_id, elo_type);
CREATE INDEX IF NOT EXISTS idx_elo_history_fight ON elo_history(fight_id);
"""


@dataclass
class RatingState:
    """In-memory tracker for a fighter's rating in a given ELO track."""
    rating: float = INITIAL_ELO
    fights: int = 0


def backfill(db_path: str | Path = DB_PATH) -> dict:
    """
    Process all fights chronologically and compute both unified and
    per-weight-class ELO ratings.

    Returns summary stats.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(ELO_TABLES_SCHEMA)

    # Clear previous ELO data
    conn.execute("DELETE FROM elo_history")
    conn.execute("DELETE FROM current_elo")

    # Load all fights chronologically
    fights = conn.execute(
        """SELECT f.id, f.event_date, f.fighter_a_id, f.fighter_b_id,
                  f.winner_id, f.result, f.weight_class,
                  f.is_title_fight, f.method, f.finish_round
           FROM fights f
           ORDER BY f.event_date ASC, f.id ASC"""
    ).fetchall()

    # In-memory rating state: {(fighter_id, elo_type): RatingState}
    ratings: dict[tuple[int, str], RatingState] = {}

    def get_state(fighter_id: int, elo_type: str) -> RatingState:
        key = (fighter_id, elo_type)
        if key not in ratings:
            ratings[key] = RatingState()
        return ratings[key]

    # Batch inserts for performance
    history_rows = []
    processed = 0
    skipped = 0

    for fight in fights:
        result = fight["result"]
        if result in ("nc", "unknown"):
            skipped += 1
            continue

        fa_id = fight["fighter_a_id"]
        fb_id = fight["fighter_b_id"]
        is_title = bool(fight["is_title_fight"])
        method = fight["method"] or ""
        finish_round = fight["finish_round"]
        weight_class = fight["weight_class"] or "Unknown"

        # Score: 1.0 = A wins, 0.0 = A loses, 0.5 = draw
        if result == "win_a":
            score_a = 1.0
        elif result == "draw":
            score_a = 0.5
        else:
            skipped += 1
            continue

        k = calculate_k(method, is_title, finish_round)

        # Update both tracks: unified + weight class
        for elo_type in ["unified", weight_class]:
            state_a = get_state(fa_id, elo_type)
            state_b = get_state(fb_id, elo_type)

            old_a, old_b = state_a.rating, state_b.rating
            new_a, new_b = update_ratings(old_a, old_b, score_a, k)

            state_a.rating = new_a
            state_a.fights += 1
            state_b.rating = new_b
            state_b.fights += 1

            history_rows.append((fa_id, fight["id"], elo_type, old_a, new_a, fight["event_date"]))
            history_rows.append((fb_id, fight["id"], elo_type, old_b, new_b, fight["event_date"]))

        processed += 1

    # Bulk insert
    conn.executemany(
        "INSERT INTO elo_history (fighter_id, fight_id, elo_type, elo_before, elo_after, fight_date) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        history_rows,
    )

    # Write current ratings
    for (fighter_id, elo_type), state in ratings.items():
        conn.execute(
            "INSERT OR REPLACE INTO current_elo (fighter_id, elo_type, rating, fights_count) "
            "VALUES (?, ?, ?, ?)",
            (fighter_id, elo_type, state.rating, state.fights),
        )

    conn.commit()
    conn.close()

    return {
        "fights_processed": processed,
        "fights_skipped": skipped,
        "fighters_rated": len({k[0] for k in ratings}),
        "elo_tracks": len({k[1] for k in ratings}),
    }


# ── Leaderboard ─────────────────────────────────────────────────────────────

def leaderboard(elo_type: str = "unified", limit: int = 50,
                min_fights: int = 5, db_path: str | Path = DB_PATH) -> list[dict]:
    """Return ranked fighters for a given ELO track."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """SELECT f.name, ce.rating, ce.fights_count
           FROM current_elo ce
           JOIN fighters f ON f.id = ce.fighter_id
           WHERE ce.elo_type = ? AND ce.fights_count >= ?
           ORDER BY ce.rating DESC
           LIMIT ?""",
        (elo_type, min_fights, limit),
    ).fetchall()
    conn.close()
    return [
        {"rank": i + 1, "name": r["name"], "elo": round(r["rating"], 1),
         "fights": r["fights_count"]}
        for i, r in enumerate(rows)
    ]


def get_trajectory(fighter_name: str, elo_type: str = "unified",
                   db_path: str | Path = DB_PATH) -> list[dict]:
    """Return ELO trajectory for a fighter: [{date, elo_before, elo_after}, …]."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """SELECT eh.fight_date, eh.elo_before, eh.elo_after
           FROM elo_history eh
           JOIN fighters f ON f.id = eh.fighter_id
           WHERE f.name = ? AND eh.elo_type = ?
           ORDER BY eh.fight_date ASC, eh.id ASC""",
        (fighter_name, elo_type),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def weight_classes(db_path: str | Path = DB_PATH) -> list[str]:
    """Return all weight classes that have ELO data."""
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT DISTINCT elo_type FROM current_elo WHERE elo_type != 'unified' ORDER BY elo_type"
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]


def search_fighter(query: str, db_path: str | Path = DB_PATH) -> list[str]:
    """Fuzzy search for fighter names."""
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT name FROM fighters WHERE name LIKE ? ORDER BY name LIMIT 20",
        (f"%{query}%",),
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]
