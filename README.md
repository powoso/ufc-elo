# UFC ELO Rating System

A full-stack ELO rating system for UFC fighters. Scrapes all historical UFC fights from ufcstats.com, computes ELO ratings with an adaptive K-factor, and serves everything through a dark-themed React web app.

## Features

- **8,500+ fights** scraped from ufcstats.com (1993–present)
- **Adaptive K-factor** adjusting for finishes, title fights, and round of finish
- **Dual ELO tracks** — per-weight-class ratings + unified cross-division rating
- **Web app** with rankings, fighter profiles, ELO trajectory charts, and a fight predictor
- **CLI** for scraping, backfilling, leaderboards, predictions, and chart generation

## Quick Start

### Prerequisites

- Python 3.10+
- Node.js 18+
- npm

### 1. Clone the repo

```bash
git clone https://github.com/powoso/ufc-elo.git
cd ufc-elo
```

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 3. Scrape fights and compute ELO ratings

```bash
python main.py scrape      # scrapes all UFC events (~10 min, cached after first run)
python main.py backfill    # computes ELO ratings for all fights
```

Or run both at once:

```bash
python main.py all         # scrape + backfill + generate leaderboard charts
```

This creates `ufc_fights.db` with all fight data and computed ratings.

### 4. Start the web app

Open two terminals:

**Terminal 1 — API server:**
```bash
python api.py
```
Starts the Flask API on `http://localhost:5001`.

**Terminal 2 — Frontend dev server:**
```bash
cd web
npm install
npm run dev
```
Opens the React app on `http://localhost:5173`. The Vite dev server proxies `/api` requests to Flask automatically.

## Web App Pages

### Rankings
Browse the ELO leaderboard across all divisions. Click division tabs to filter by weight class. Features inline sparkline charts and color-coded ELO tiers.

### Fighter Profile
Click any fighter to see their full profile — ELO trajectory chart, win/loss record, peak rating, per-division breakdowns, and a reverse-chronological fight log with ELO changes per bout.

### Fight Predictor
Select two fighters to see head-to-head win probability based on their current ELO ratings, plus implied American odds (moneyline).

## CLI Usage

```bash
python main.py scrape                           # scrape fights from ufcstats.com
python main.py backfill                         # compute ELO ratings
python main.py leaderboard                      # top 50 unified leaderboard
python main.py leaderboard --class Lightweight  # weight class leaderboard
python main.py predict "Jon Jones" "Tom Aspinall"
python main.py chart "Jon Jones" "Islam Makhachev" "Georges St-Pierre"
python main.py classes                          # list available weight classes
python main.py search "Conor"                   # fuzzy fighter search
```

## How the ELO System Works

Standard ELO with multiplicative K-factor adjustments:

| Factor | Multiplier |
|--------|-----------|
| Base K | 32 |
| Finish (KO/TKO/Sub) | ×1.5 |
| Title fight | ×1.25 |
| Round 1 finish | ×1.3 |
| Round 2 finish | ×1.2 |
| Round 3 finish | ×1.1 |
| Round 4 finish | ×1.05 |
| Round 5 finish | ×1.0 |

A first-round KO in a title fight produces K = 32 × 1.5 × 1.25 × 1.3 = **78**, compared to K = 32 for a standard decision.

All fighters start at 1500. Win probability uses the standard logistic formula:

```
P(A wins) = 1 / (1 + 10^((Rb - Ra) / 400))
```

## Project Structure

```
ufc-elo/
├── scrape.py          # ufcstats.com scraper
├── elo.py             # ELO engine (backfill, predict, leaderboard)
├── charts.py          # matplotlib chart generation
├── main.py            # CLI entry point
├── api.py             # Flask API server
├── requirements.txt   # Python dependencies
├── ufc_fights.db      # SQLite database (generated, not in repo)
├── cache/             # scraped HTML cache (generated)
├── output/            # chart PNGs (generated)
└── web/               # React frontend
    ├── src/
    │   ├── App.jsx        # routing + navbar with search
    │   ├── Rankings.jsx   # leaderboard page
    │   ├── Fighter.jsx    # fighter profile page
    │   ├── Predict.jsx    # fight predictor page
    │   ├── index.css      # full design system
    │   └── main.jsx       # entry point
    ├── package.json
    └── vite.config.js     # dev server + API proxy config
```

## Tech Stack

- **Backend:** Python, Flask, SQLite, BeautifulSoup
- **Frontend:** React 19, Vite, React Router, Recharts
- **Styling:** Custom CSS with dark MMA theme
