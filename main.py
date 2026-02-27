#!/usr/bin/env python3
"""
UFC ELO Rating System — Main CLI

Usage:
    python main.py scrape        # Scrape all UFC fights into SQLite
    python main.py backfill      # Calculate ELO ratings for all fights
    python main.py leaderboard   # Print top-50 unified leaderboard
    python main.py leaderboard --class "Lightweight"  # Weight class leaderboard
    python main.py predict "Fighter A" "Fighter B"    # Win probability
    python main.py chart "Fighter A" "Fighter B"      # ELO trajectory chart
    python main.py chart "Fighter A" --class Lightweight
    python main.py all           # Scrape + backfill + generate all outputs
"""

import argparse
import sys
from pathlib import Path

from elo import backfill, leaderboard, predict, weight_classes, search_fighter, DB_PATH
from charts import plot_trajectory, plot_leaderboard_bar


def cmd_scrape(args):
    from scrape import scrape_all
    scrape_all(force=args.force)


def cmd_backfill(args):
    if not DB_PATH.exists():
        print(f"Database not found at {DB_PATH}. Run 'scrape' first.")
        sys.exit(1)
    print("Running ELO backfill...")
    stats = backfill()
    print(f"  Fights processed: {stats['fights_processed']}")
    print(f"  Fights skipped (NC/unknown): {stats['fights_skipped']}")
    print(f"  Fighters rated: {stats['fighters_rated']}")
    print(f"  ELO tracks: {stats['elo_tracks']}")
    print("Done.")


def cmd_leaderboard(args):
    elo_type = args.weight_class or "unified"
    min_fights = args.min_fights
    limit = args.limit

    rankings = leaderboard(elo_type=elo_type, limit=limit, min_fights=min_fights)
    if not rankings:
        print(f"No data for elo_type={elo_type!r}. Available weight classes:")
        for wc in weight_classes():
            print(f"  - {wc}")
        sys.exit(1)

    # Print table
    label = elo_type if elo_type != "unified" else "Unified Cross-Division"
    print(f"\n{'═' * 55}")
    print(f"  UFC ELO LEADERBOARD — {label}")
    print(f"  (min {min_fights} fights)")
    print(f"{'═' * 55}")
    print(f"  {'Rank':<6}{'Fighter':<30}{'ELO':>8}{'Fights':>8}")
    print(f"  {'─' * 52}")
    for r in rankings:
        print(f"  {r['rank']:<6}{r['name']:<30}{r['elo']:>8.1f}{r['fights']:>8}")
    print(f"{'═' * 55}\n")

    # Also generate chart
    plot_leaderboard_bar(rankings, elo_type=elo_type, top_n=min(25, limit))


def cmd_predict(args):
    fighter_a = args.fighter_a
    fighter_b = args.fighter_b
    elo_type = args.weight_class or "unified"

    try:
        result = predict(fighter_a, fighter_b, elo_type=elo_type)
    except ValueError as e:
        print(f"Error: {e}")
        # Try fuzzy search
        for name in [fighter_a, fighter_b]:
            matches = search_fighter(name)
            if matches:
                print(f"  Did you mean: {', '.join(matches[:5])}")
        sys.exit(1)

    a = result["fighter_a"]
    b = result["fighter_b"]

    print(f"\n{'═' * 50}")
    print(f"  PREDICTION ({result['elo_type']})")
    print(f"{'═' * 50}")
    print(f"  {a['name']:<28} vs {b['name']}")
    print(f"  ELO: {a['elo']:<24}     ELO: {b['elo']}")
    print(f"  Win: {a['win_prob']*100:>5.1f}%{' '*19}Win: {b['win_prob']*100:>5.1f}%")
    print(f"{'═' * 50}\n")

    # Visual probability bar
    bar_len = 40
    a_fill = int(a["win_prob"] * bar_len)
    b_fill = bar_len - a_fill
    bar = f"  [{'█' * a_fill}{'░' * b_fill}]"
    print(bar)
    print(f"  {a['name'].split()[-1]:<20}{' ' * (bar_len - 20)}{b['name'].split()[-1]:>20}")
    print()


def cmd_chart(args):
    fighters = args.fighters
    elo_type = args.weight_class or "unified"
    plot_trajectory(fighters, elo_type=elo_type)


def cmd_classes(args):
    classes = weight_classes()
    print(f"\nAvailable weight classes ({len(classes)}):")
    for wc in classes:
        print(f"  - {wc}")
    print()


def cmd_search(args):
    matches = search_fighter(args.query)
    if matches:
        print(f"\nFighters matching '{args.query}':")
        for m in matches:
            print(f"  - {m}")
    else:
        print(f"No fighters found matching '{args.query}'")
    print()


def cmd_all(args):
    # Scrape
    from scrape import scrape_all
    scrape_all()

    # Backfill
    print("\n" + "=" * 60)
    print("Running ELO backfill...")
    stats = backfill()
    print(f"  Fights processed: {stats['fights_processed']}")
    print(f"  Fighters rated: {stats['fighters_rated']}")
    print(f"  ELO tracks: {stats['elo_tracks']}")

    # Unified leaderboard
    print("\n" + "=" * 60)
    rankings = leaderboard(elo_type="unified", limit=50, min_fights=5)
    label = "Unified Cross-Division"
    print(f"\n  UFC ELO LEADERBOARD — {label}")
    print(f"  {'Rank':<6}{'Fighter':<30}{'ELO':>8}{'Fights':>8}")
    print(f"  {'─' * 52}")
    for r in rankings[:30]:
        print(f"  {r['rank']:<6}{r['name']:<30}{r['elo']:>8.1f}{r['fights']:>8}")

    # Charts for top fighters
    print("\n" + "=" * 60)
    print("Generating charts...")
    plot_leaderboard_bar(rankings, elo_type="unified", top_n=25)

    # Trajectory chart for top 5
    if rankings:
        top5 = [r["name"] for r in rankings[:5]]
        plot_trajectory(top5, elo_type="unified")

    # Per-weight-class leaderboards
    for wc in weight_classes():
        wc_rankings = leaderboard(elo_type=wc, limit=10, min_fights=3)
        if wc_rankings:
            plot_leaderboard_bar(wc_rankings, elo_type=wc, top_n=10)

    print("\nAll outputs saved to ./output/")


def main():
    parser = argparse.ArgumentParser(description="UFC ELO Rating System")
    subs = parser.add_subparsers(dest="command")

    # scrape
    p_scrape = subs.add_parser("scrape", help="Scrape UFC fights from ufcstats.com")
    p_scrape.add_argument("--force", action="store_true", help="Re-scrape all events")

    # backfill
    subs.add_parser("backfill", help="Calculate ELO ratings")

    # leaderboard
    p_lb = subs.add_parser("leaderboard", help="Show ranked leaderboard")
    p_lb.add_argument("--class", dest="weight_class", help="Weight class (default: unified)")
    p_lb.add_argument("--min-fights", type=int, default=5, help="Minimum fights (default: 5)")
    p_lb.add_argument("--limit", type=int, default=50, help="Number of results (default: 50)")

    # predict
    p_pred = subs.add_parser("predict", help="Predict fight outcome")
    p_pred.add_argument("fighter_a", help="First fighter name")
    p_pred.add_argument("fighter_b", help="Second fighter name")
    p_pred.add_argument("--class", dest="weight_class", help="ELO type (default: unified)")

    # chart
    p_chart = subs.add_parser("chart", help="Generate ELO trajectory chart")
    p_chart.add_argument("fighters", nargs="+", help="Fighter name(s)")
    p_chart.add_argument("--class", dest="weight_class", help="ELO type (default: unified)")

    # classes
    subs.add_parser("classes", help="List weight classes")

    # search
    p_search = subs.add_parser("search", help="Search for a fighter")
    p_search.add_argument("query", help="Search query")

    # all
    subs.add_parser("all", help="Scrape + backfill + generate all outputs")

    args = parser.parse_args()

    commands = {
        "scrape": cmd_scrape,
        "backfill": cmd_backfill,
        "leaderboard": cmd_leaderboard,
        "predict": cmd_predict,
        "chart": cmd_chart,
        "classes": cmd_classes,
        "search": cmd_search,
        "all": cmd_all,
    }

    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
