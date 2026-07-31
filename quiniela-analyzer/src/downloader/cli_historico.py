"""CLI: descargar histórico de partidos LaLiga desde football-data.co.uk."""
from __future__ import annotations

import argparse
import logging

from .football_data import default_seasons, run_historico


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", default=None, help="Ruta a SQLite (opcional)")
    p.add_argument(
        "--divisions", nargs="+", default=["SP1", "SP2"],
        help="Divisiones a descargar (default: SP1 SP2)",
    )
    p.add_argument(
        "--from-year", type=int, default=2010,
        help="Año inicio (default 2010)",
    )
    p.add_argument(
        "--to-year", type=int, default=2025,
        help="Año final inclusive (default 2025)",
    )
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    seasons = [
        s for s in default_seasons()
        if args.from_year <= s.start_year <= args.to_year
    ]
    results = run_historico(seasons=seasons, divisions=tuple(args.divisions), db_path=args.db)

    total_inserted = total_skipped = 0
    print()
    print(f"{'Season':6} {'Div':4} {'Inserted':>9} {'Skipped':>8}")
    print("-" * 32)
    for season, divs in results.items():
        for div, (ins, skp) in divs.items():
            print(f"{season:6} {div:4} {ins:>9} {skp:>8}")
            total_inserted += ins
            total_skipped += skp
    print("-" * 32)
    print(f"{'TOTAL':6} {'':4} {total_inserted:>9} {total_skipped:>8}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())