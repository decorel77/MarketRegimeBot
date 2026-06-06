"""CLI entrypoint for the MarketRegimeBot dry-run cycle."""

from __future__ import annotations

import argparse
import json

from workflow.regime_cycle import run_regime_cycle


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run one safe MarketRegimeBot dry-run cycle."
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run one dry-run regime cycle and exit.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.once:
        parser.error("Only --once is supported in the skeleton phase.")
    result = run_regime_cycle(write_snapshot=True)
    print(
        json.dumps(
            {
                "status": result["status"],
                "dry_run": result["dry_run"],
                "regime": result["regime"],
                "confidence": result["confidence"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

