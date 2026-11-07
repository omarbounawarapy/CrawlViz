"""Run one load crawl in this process, write the report as JSON and judge it.

    python -m tests.load.run --pages 200 --run smoke --report smoke.json
    python -m tests.load.run --pages 50000 --run full --report full.json > /dev/null

The run is judged against its entry in ``budget.json``. The exit status is 0 within budget,
1 when a limit is broken and 2 when the crawl itself failed (it timed out or ended before
its page budget), so a script or CI step can use it directly. The crawler's own debug
trace goes to standard output, which is why the report is a file and not a printed line.
Peak RSS is a per-process maximum, so each run gets a process of its own.
"""

import argparse
import asyncio
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

from tests.load.budget import BUDGET_FILE, check_budget, load_budget
from tests.load.crawl import CrawlEndedEarlyError, run_load_crawl

EXIT_WITHIN_BUDGET = 0
EXIT_OVER_BUDGET = 1
EXIT_CRAWL_FAILED = 2


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one load crawl and judge it.")
    parser.add_argument("--pages", type=int, required=True, help="page budget of the crawl")
    parser.add_argument("--run", required=True, help="entry of budget.json to judge against")
    parser.add_argument(
        "--budget", type=Path, default=BUDGET_FILE, help="limits file (default: budget.json)"
    )
    parser.add_argument("--report", type=Path, required=True, help="file for the JSON report")
    return parser.parse_args(argv)


def write_report(path: Path, report: dict[str, Any]) -> None:  # Any: the JSON report
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    limits = load_budget(args.budget).for_run(args.run)
    try:
        with tempfile.TemporaryDirectory(prefix="crawlviz-load-") as work_dir:
            measurement = asyncio.run(
                run_load_crawl(args.pages, Path(work_dir), limits.max_wall_seconds)
            )
    except (TimeoutError, CrawlEndedEarlyError) as failure:
        reason = str(failure) or f"the crawl ran past {limits.max_wall_seconds:g} s"
        write_report(args.report, {"run": args.run, "crawl_failed": reason})
        print(f"load run {args.run}: crawl failed: {reason}", file=sys.stderr)
        return EXIT_CRAWL_FAILED
    problems = check_budget(measurement, limits)
    write_report(
        args.report,
        {"run": args.run, "measurement": measurement.to_json(), "problems": problems},
    )
    for problem in problems:
        print(f"load run {args.run}: over budget: {problem}", file=sys.stderr)
    return EXIT_OVER_BUDGET if problems else EXIT_WITHIN_BUDGET


if __name__ == "__main__":
    sys.exit(main())
