import argparse
import json
from datetime import datetime, timezone

from .config import SOURCES
from .pipeline import BriefConfig, generate_brief
from .sources import FixtureFetcher


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Generate a read-only Milou news brief.")
    parser.add_argument("--fixture", required=True, help="JSON fixture mapping source name to article arrays")
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args(argv)
    with open(args.fixture, encoding="utf-8") as handle:
        payload = json.load(handle)
    print(generate_brief(SOURCES, FixtureFetcher(payload), config=BriefConfig(limit=args.limit)), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
