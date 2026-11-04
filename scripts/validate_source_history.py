"""Fail before source-index setup or coverage when fixed history/binding is invalid."""

import argparse
from pathlib import Path

from tests.source_history import HISTORY, validate_source_history


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history-directory", type=Path, default=HISTORY)
    args = parser.parse_args()
    validate_source_history(args.history_directory)
    print("Historical source roots and current Sticky binding validated.")


if __name__ == "__main__":
    main()
