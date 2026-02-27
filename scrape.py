"""
Scraper for ufcstats.com — pulls full UFC fight history into SQLite.

Fetches the completed-events index, then each event page for fight details.
Caches raw HTML to disk so re-runs don't re-fetch pages already downloaded.
"""

import hashlib
import json
import os
import re
import sqlite3
import time
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE_URL = "http://ufcstats.com"
EVENTS_URL = f"{BASE_URL}/statistics/events/completed?page=all"
CACHE_DIR = Path(__file__).parent / "cache"
DB_PATH = Path(__file__).parent / "ufc_fights.db"
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
DELAY = 0.4  # seconds between requests


# ── Caching ──────────────────────────────────────────────────────────────────

def _cache_key(url: str) -> Path:
    h = hashlib.md5(url.encode()).hexdigest()
    return CACHE_DIR / f"{h}.html"


def fetch(url: str, *, force: bool = False) -> str:
    """Fetch a URL, returning HTML. Uses disk cache unless force=True."""
    cached = _cache_key(url)
    if not force and cached.exists():
        return cached.read_text()
    time.sleep(DELAY)
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    cached.write_text(resp.text)
    return resp.text


# ── Parsers ──────────────────────────────────────────────────────────────────

def parse_events_index(html: str) -> list[dict]:
    """Return [{url, name, date, location}, …] sorted oldest-first."""
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.select("tr.b-statistics__table-row")
    events = []
    for row in rows:
        link_tag = row.select_one("a.b-link")
        if not link_tag:
            continue
        url = link_tag["href"].strip()
        name = link_tag.get_text(strip=True)
        cells = row.select("td")
        date_text = cells[0].get_text(strip=True).replace(name, "").strip() if cells else ""
        location = cells[1].get_text(strip=True) if len(cells) > 1 else ""
        # Parse date
        event_date = None
        for fmt in ("%B %d, %Y", "%b %d, %Y"):
            try:
                event_date = datetime.strptime(date_text, fmt).strftime("%Y-%m-%d")
                break
            except ValueError:
                continue
        events.append({
            "url": url,
            "name": name,
            "date": event_date,
            "location": location,
        })
    # Sort chronologically (oldest first) for ELO backfill
    events = [e for e in events if e["date"]]
    events.sort(key=lambda e: e["date"])
    return events


def parse_event_fights(html: str, event_name: str, event_date: str) -> list[dict]:
    """Parse all fights from an event detail page."""
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.select("tr.b-fight-details__table-row")
    fights = []
    for row in rows:
        cols = row.select("td")
        if len(cols) < 10:
            continue  # header or malformed

        # ── Result flags ─────────────────────────────────────────────
        # Win rows have 1 flag ("win" for winner); NC/draw have 2 flags
        result_col = cols[0]
        flags = [f.get_text(strip=True).lower() for f in result_col.select("i.b-flag__text")]
        if not flags:
            continue

        # ── Title fight? (belt icon in weight class column) ──────────
        is_title = bool(row.select("img[src*='belt']"))

        # ── Fighter names ────────────────────────────────────────────
        name_col = cols[1]
        fighter_links = name_col.select("a")
        if len(fighter_links) < 2:
            continue
        fighter_a = fighter_links[0].get_text(strip=True)
        fighter_b = fighter_links[1].get_text(strip=True)

        # ── Weight class ─────────────────────────────────────────────
        wc_col = cols[6]
        weight_class = wc_col.get_text(strip=True)

        # ── Method ───────────────────────────────────────────────────
        method_col = cols[7]
        method_parts = [p.get_text(strip=True) for p in method_col.select("p")]
        method = method_parts[0] if method_parts else ""
        method_detail = method_parts[1] if len(method_parts) > 1 else ""

        # ── Round & Time ─────────────────────────────────────────────
        round_col = cols[8]
        finish_round = round_col.get_text(strip=True)
        time_col = cols[9]
        finish_time = time_col.get_text(strip=True)

        # ── Determine winner ─────────────────────────────────────────
        # Winner is always listed first on ufcstats.com
        if len(flags) == 1 and flags[0] == "win":
            winner = fighter_a
            result = "win_a"
        elif len(flags) >= 2 and flags[0] == "nc":
            winner = None
            result = "nc"
        elif len(flags) >= 2 and flags[0] == "draw":
            winner = None
            result = "draw"
        else:
            winner = None
            result = "unknown"

        try:
            finish_round_int = int(finish_round)
        except (ValueError, TypeError):
            finish_round_int = None

        fights.append({
            "event_name": event_name,
            "event_date": event_date,
            "fighter_a": fighter_a,
            "fighter_b": fighter_b,
            "winner": winner,
            "result": result,
            "weight_class": weight_class,
            "is_title_fight": is_title,
            "method": method,
            "method_detail": method_detail,
            "finish_round": finish_round_int,
            "finish_time": finish_time,
        })

    return fights


# ── Database ─────────────────────────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS fighters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS fights (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_name TEXT NOT NULL,
    event_date TEXT NOT NULL,
    fighter_a_id INTEGER NOT NULL REFERENCES fighters(id),
    fighter_b_id INTEGER NOT NULL REFERENCES fighters(id),
    winner_id INTEGER REFERENCES fighters(id),
    result TEXT NOT NULL,
    weight_class TEXT,
    is_title_fight INTEGER DEFAULT 0,
    method TEXT,
    method_detail TEXT,
    finish_round INTEGER,
    finish_time TEXT
);

CREATE INDEX IF NOT EXISTS idx_fights_date ON fights(event_date);
CREATE INDEX IF NOT EXISTS idx_fights_fighter_a ON fights(fighter_a_id);
CREATE INDEX IF NOT EXISTS idx_fights_fighter_b ON fights(fighter_b_id);
"""


def init_db(db_path: str | Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def get_or_create_fighter(conn: sqlite3.Connection, name: str) -> int:
    row = conn.execute("SELECT id FROM fighters WHERE name = ?", (name,)).fetchone()
    if row:
        return row[0]
    cur = conn.execute("INSERT INTO fighters (name) VALUES (?)", (name,))
    return cur.lastrowid


def insert_fight(conn: sqlite3.Connection, fight: dict) -> None:
    fa_id = get_or_create_fighter(conn, fight["fighter_a"])
    fb_id = get_or_create_fighter(conn, fight["fighter_b"])
    winner_id = None
    if fight["winner"]:
        winner_id = get_or_create_fighter(conn, fight["winner"])

    conn.execute(
        """INSERT INTO fights
           (event_name, event_date, fighter_a_id, fighter_b_id, winner_id,
            result, weight_class, is_title_fight, method, method_detail,
            finish_round, finish_time)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            fight["event_name"], fight["event_date"],
            fa_id, fb_id, winner_id,
            fight["result"], fight["weight_class"],
            int(fight["is_title_fight"]),
            fight["method"], fight["method_detail"],
            fight["finish_round"], fight["finish_time"],
        ),
    )


# ── Main ─────────────────────────────────────────────────────────────────────

def scrape_all(force: bool = False):
    """Scrape all UFC events and fights into the SQLite database."""
    CACHE_DIR.mkdir(exist_ok=True)

    print("Fetching events index...")
    events_html = fetch(EVENTS_URL, force=force)
    events = parse_events_index(events_html)
    print(f"Found {len(events)} events")

    conn = init_db()
    # Track which events we already scraped (by event_date + name)
    existing = set(
        conn.execute("SELECT DISTINCT event_name, event_date FROM fights").fetchall()
    )

    total_fights = 0
    for i, event in enumerate(events):
        key = (event["name"], event["date"])
        if key in existing and not force:
            continue

        print(f"[{i+1}/{len(events)}] {event['date']} — {event['name']}")
        try:
            event_html = fetch(event["url"])
            fights = parse_event_fights(event_html, event["name"], event["date"])
            for fight in fights:
                insert_fight(conn, fight)
            conn.commit()
            total_fights += len(fights)
        except Exception as e:
            print(f"  ERROR: {e}")
            continue

    conn.close()
    print(f"\nDone. Inserted {total_fights} new fights.")
    print(f"Database: {DB_PATH}")


if __name__ == "__main__":
    scrape_all()
