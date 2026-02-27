"""
Flask API for the UFC ELO Rating System.

Serves leaderboard, fighter profiles, predictions, and trajectory data
from the SQLite database populated by scrape.py + elo.py.
"""

import sqlite3
from pathlib import Path

from flask import Flask, jsonify, request
from flask_cors import CORS

DB_PATH = Path(__file__).parent / "ufc_fights.db"

app = Flask(__name__)
CORS(app)


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ── Leaderboard ──────────────────────────────────────────────────────────────

@app.route("/api/leaderboard")
def api_leaderboard():
    elo_type = request.args.get("type", "unified")
    limit = int(request.args.get("limit", 50))
    min_fights = int(request.args.get("min_fights", 5))

    conn = get_db()
    rows = conn.execute(
        """SELECT f.name, ce.rating, ce.fights_count
           FROM current_elo ce
           JOIN fighters f ON f.id = ce.fighter_id
           WHERE ce.elo_type = ? AND ce.fights_count >= ?
           ORDER BY ce.rating DESC
           LIMIT ?""",
        (elo_type, min_fights, limit),
    ).fetchall()

    # Also get sparkline data (last 10 fights) for each fighter
    result = []
    for i, r in enumerate(rows):
        spark = conn.execute(
            """SELECT eh.elo_after FROM elo_history eh
               JOIN fighters f ON f.id = eh.fighter_id
               WHERE f.name = ? AND eh.elo_type = ?
               ORDER BY eh.fight_date DESC, eh.id DESC
               LIMIT 10""",
            (r["name"], elo_type),
        ).fetchall()
        sparkline = [s["elo_after"] for s in reversed(spark)]

        result.append({
            "rank": i + 1,
            "name": r["name"],
            "elo": round(r["rating"], 1),
            "fights": r["fights_count"],
            "sparkline": sparkline,
        })

    conn.close()
    return jsonify(result)


# ── Fighter Profile ──────────────────────────────────────────────────────────

@app.route("/api/fighter/<path:name>")
def api_fighter(name):
    conn = get_db()

    fighter = conn.execute("SELECT id, name FROM fighters WHERE name = ?", (name,)).fetchone()
    if not fighter:
        conn.close()
        return jsonify({"error": f"Fighter not found: {name}"}), 404

    fid = fighter["id"]

    # All ELO ratings
    elos = conn.execute(
        "SELECT elo_type, rating, fights_count FROM current_elo WHERE fighter_id = ?",
        (fid,),
    ).fetchall()
    ratings = {r["elo_type"]: {"elo": round(r["rating"], 1), "fights": r["fights_count"]} for r in elos}

    # Unified trajectory
    traj = conn.execute(
        """SELECT eh.fight_date, eh.elo_before, eh.elo_after, fi.event_name, fi.method,
                  fi.method_detail, fi.weight_class, fi.is_title_fight, fi.finish_round,
                  CASE WHEN fi.winner_id = ? THEN 'win'
                       WHEN fi.result = 'draw' THEN 'draw'
                       ELSE 'loss' END as outcome,
                  CASE WHEN fi.fighter_a_id = ? THEN fb.name ELSE fa.name END as opponent
           FROM elo_history eh
           JOIN fights fi ON fi.id = eh.fight_id
           JOIN fighters fa ON fa.id = fi.fighter_a_id
           JOIN fighters fb ON fb.id = fi.fighter_b_id
           WHERE eh.fighter_id = ? AND eh.elo_type = 'unified'
           ORDER BY eh.fight_date ASC, eh.id ASC""",
        (fid, fid, fid),
    ).fetchall()

    trajectory = []
    for t in traj:
        trajectory.append({
            "date": t["fight_date"],
            "elo_before": round(t["elo_before"], 1),
            "elo_after": round(t["elo_after"], 1),
            "event": t["event_name"],
            "opponent": t["opponent"],
            "outcome": t["outcome"],
            "method": t["method"],
            "method_detail": t["method_detail"],
            "weight_class": t["weight_class"],
            "is_title": bool(t["is_title_fight"]),
            "round": t["finish_round"],
        })

    # Record summary
    wins = sum(1 for t in trajectory if t["outcome"] == "win")
    losses = sum(1 for t in trajectory if t["outcome"] == "loss")
    draws = sum(1 for t in trajectory if t["outcome"] == "draw")
    finishes = sum(1 for t in trajectory if t["outcome"] == "win" and t["method"] in ("KO/TKO", "SUB"))

    # Peak ELO
    peak = max((t["elo_after"] for t in trajectory), default=1500)

    conn.close()
    return jsonify({
        "name": name,
        "ratings": ratings,
        "record": {"wins": wins, "losses": losses, "draws": draws, "finishes": finishes},
        "peak_elo": round(peak, 1),
        "trajectory": trajectory,
    })


# ── Prediction ───────────────────────────────────────────────────────────────

@app.route("/api/predict")
def api_predict():
    a = request.args.get("a", "")
    b = request.args.get("b", "")
    elo_type = request.args.get("type", "unified")

    if not a or not b:
        return jsonify({"error": "Both fighter names required (?a=...&b=...)"}), 400

    conn = get_db()

    def get_elo(name):
        row = conn.execute(
            """SELECT ce.rating, ce.fights_count FROM current_elo ce
               JOIN fighters f ON f.id = ce.fighter_id
               WHERE f.name = ? AND ce.elo_type = ?""",
            (name, elo_type),
        ).fetchone()
        return row

    ra_row = get_elo(a)
    rb_row = get_elo(b)
    conn.close()

    if not ra_row:
        return jsonify({"error": f"Fighter not found: {a}"}), 404
    if not rb_row:
        return jsonify({"error": f"Fighter not found: {b}"}), 404

    ra, rb = ra_row["rating"], rb_row["rating"]
    prob_a = 1.0 / (1.0 + 10.0 ** ((rb - ra) / 400.0))

    return jsonify({
        "fighter_a": {"name": a, "elo": round(ra, 1), "win_prob": round(prob_a, 4),
                      "fights": ra_row["fights_count"]},
        "fighter_b": {"name": b, "elo": round(rb, 1), "win_prob": round(1 - prob_a, 4),
                      "fights": rb_row["fights_count"]},
        "elo_type": elo_type,
    })


# ── Trajectory (multi-fighter) ───────────────────────────────────────────────

@app.route("/api/trajectory")
def api_trajectory():
    names = request.args.get("fighters", "").split(",")
    elo_type = request.args.get("type", "unified")
    names = [n.strip() for n in names if n.strip()]

    if not names:
        return jsonify({"error": "Provide ?fighters=Name1,Name2,..."}), 400

    conn = get_db()
    result = {}
    for name in names[:8]:  # max 8 fighters
        rows = conn.execute(
            """SELECT eh.fight_date, eh.elo_before, eh.elo_after
               FROM elo_history eh
               JOIN fighters f ON f.id = eh.fighter_id
               WHERE f.name = ? AND eh.elo_type = ?
               ORDER BY eh.fight_date ASC, eh.id ASC""",
            (name, elo_type),
        ).fetchall()
        if rows:
            points = [{"date": rows[0]["fight_date"], "elo": round(rows[0]["elo_before"], 1)}]
            for r in rows:
                points.append({"date": r["fight_date"], "elo": round(r["elo_after"], 1)})
            result[name] = points

    conn.close()
    return jsonify(result)


# ── Search ───────────────────────────────────────────────────────────────────

@app.route("/api/search")
def api_search():
    q = request.args.get("q", "")
    if len(q) < 2:
        return jsonify([])

    conn = get_db()
    rows = conn.execute(
        """SELECT f.name, ce.rating, ce.fights_count
           FROM fighters f
           LEFT JOIN current_elo ce ON ce.fighter_id = f.id AND ce.elo_type = 'unified'
           WHERE f.name LIKE ?
           ORDER BY ce.rating DESC
           LIMIT 15""",
        (f"%{q}%",),
    ).fetchall()
    conn.close()

    return jsonify([{
        "name": r["name"],
        "elo": round(r["rating"], 1) if r["rating"] else None,
        "fights": r["fights_count"] or 0,
    } for r in rows])


# ── Weight Classes ───────────────────────────────────────────────────────────

@app.route("/api/weight-classes")
def api_weight_classes():
    conn = get_db()
    rows = conn.execute(
        """SELECT elo_type, COUNT(*) as fighters
           FROM current_elo
           WHERE elo_type != 'unified'
           GROUP BY elo_type
           ORDER BY fighters DESC"""
    ).fetchall()
    conn.close()
    return jsonify([{"name": r["elo_type"], "fighters": r["fighters"]} for r in rows])


# ── Stats ────────────────────────────────────────────────────────────────────

@app.route("/api/stats")
def api_stats():
    conn = get_db()
    fighters = conn.execute("SELECT COUNT(*) FROM fighters").fetchone()[0]
    fights = conn.execute("SELECT COUNT(*) FROM fights").fetchone()[0]
    title_fights = conn.execute("SELECT COUNT(*) FROM fights WHERE is_title_fight = 1").fetchone()[0]
    date_range = conn.execute("SELECT MIN(event_date), MAX(event_date) FROM fights").fetchone()
    conn.close()

    return jsonify({
        "total_fighters": fighters,
        "total_fights": fights,
        "title_fights": title_fights,
        "date_from": date_range[0],
        "date_to": date_range[1],
    })


if __name__ == "__main__":
    app.run(port=5001, debug=True)
