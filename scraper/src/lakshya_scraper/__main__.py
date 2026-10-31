"""Command line for the scraper.

    uv run python -m lakshya_scraper run jobsnepal --dry-run --limit 3   # print, save nothing
    uv run python -m lakshya_scraper run jobsnepal                       # real run, saves jobs
    uv run python -m lakshya_scraper reclean --dry-run                   # show what would change
    uv run python -m lakshya_scraper reclean                             # re-clean stored jobs

Logs go to stderr and results to stdout, so the output can be piped (e.g. into jq).
"""

import argparse
import json
import logging
import sys
from dataclasses import asdict

from lakshya_backend.db.session import get_session
from lakshya_scraper.pipeline import SourceBusy, preview_source, run_source
from lakshya_scraper.reclean import reclean
from lakshya_scraper.scrapers import SCRAPERS

_DESCRIPTION_PREVIEW = 300  # characters of the description to print in a dry run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m lakshya_scraper")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="scrape one source")
    run.add_argument("slug", choices=sorted(SCRAPERS), help="source to scrape")
    run.add_argument("--dry-run", action="store_true", help="fetch, parse and clean; save nothing")
    run.add_argument("--limit", type=int, help="open at most this many job pages")
    recleaning = commands.add_parser(
        "reclean", help="re-clean stored jobs from their saved raw text"
    )
    recleaning.add_argument(
        "--dry-run", action="store_true", help="show what would change; save nothing"
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    if args.command == "reclean":
        with get_session() as session:
            result = reclean(session, dry_run=args.dry_run)
        print(json.dumps(asdict(result), indent=2, ensure_ascii=False, default=str))
        return 0

    if args.dry_run:
        for preview in preview_source(args.slug, limit=args.limit or 3):
            print(json.dumps(_preview_as_dict(preview), indent=2, ensure_ascii=False))
        return 0

    try:
        result = run_source(args.slug, limit=args.limit)
    except SourceBusy as busy:
        print(busy, file=sys.stderr)
        return 1
    print(json.dumps(asdict(result), indent=2))
    return 0 if result.problem is None else 1  # non-zero tells a scheduler something is wrong


def _preview_as_dict(preview) -> dict:
    output: dict = {"url": preview.item.url, "error": preview.error}
    if preview.raw:
        raw = preview.raw.model_dump(mode="json")
        raw["description"] = (raw["description"] or "")[:_DESCRIPTION_PREVIEW]
        output["raw"] = raw
    if preview.raw and not preview.error:
        if preview.job:
            output["clean"] = preview.job.model_dump(mode="json", exclude={"description"})
        else:
            output["clean"] = "skipped (not a job, or outside Nepal)"
    return output


if __name__ == "__main__":
    raise SystemExit(main())
