"""CLI for the research-only calibration / walk-forward harness (QA-014).

RESEARCH / REPORTING ONLY — reads local history files, never the network,
never broker state. See docs/research/calibration_harness.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from research.calibration_harness import (
    CalibrationDataError,
    CalibrationWriteGuardError,
    build_calibration_report,
    load_history_csv,
    load_history_json,
    write_calibration_report,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the RESEARCH-ONLY historical calibration / walk-forward "
            "harness on a local history file."
        )
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--csv", help="Local history CSV (date,spy_close,qqq_close,vix_close).")
    source.add_argument("--json", help="Local history JSON (list of row objects, same columns).")
    parser.add_argument(
        "--out",
        default=None,
        help="Write the full report JSON here (e.g. data/research/calibration_report.json).",
    )
    parser.add_argument("--forward-horizon", type=int, default=5)
    parser.add_argument("--train-size", type=int, default=40)
    parser.add_argument("--test-size", type=int, default=20)
    parser.add_argument(
        "--model",
        choices=["v1", "v2"],
        default="v1",
        help="Regime model to evaluate: v1 (production, default) or v2 (QA-012 research model).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.csv:
            history = load_history_csv(Path(args.csv))
            source_label = f"historical_csv:{Path(args.csv).name}"
        else:
            history = load_history_json(Path(args.json))
            source_label = f"historical_json:{Path(args.json).name}"
        report = build_calibration_report(
            history,
            source_label=source_label,
            forward_horizon=args.forward_horizon,
            train_size=args.train_size,
            test_size=args.test_size,
            model_version=args.model,
        )
        if args.out:
            written = write_calibration_report(report, Path(args.out))
            print(
                json.dumps(
                    {
                        "written_to": str(written),
                        "schema_version": report["schema_version"],
                        "model_version": args.model,
                        "research_only": True,
                        "records_classified": report["calibration"]["records_classified"],
                        "fold_count": report["walk_forward"]["fold_count"],
                    },
                    sort_keys=True,
                )
            )
        else:
            print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    except (CalibrationDataError, CalibrationWriteGuardError) as exc:
        print(
            json.dumps(
                {
                    "error": "calibration_failed_closed",
                    "detail": str(exc),
                    "research_only": True,
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
