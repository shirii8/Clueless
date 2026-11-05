"""Print the data-quality report for the seed files without touching the database.

Usage: docker compose run --rm api python -m app.import_seed   (or: make seed-report)
"""
import argparse
from pathlib import Path

from app.config import seed_dir
from app.seed import validate_seed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed-dir", type=Path, default=seed_dir())
    args = parser.parse_args()
    print("Data quality report")
    for line in validate_seed(args.seed_dir):
        print(f"- {line}")


if __name__ == "__main__":
    main()
