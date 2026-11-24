#!/usr/bin/env python3
"""Inspect a Win16 NE file without executing it; optionally extract raw resources."""
from pathlib import Path
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from opencardshop.ne import inspect_ne

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path, nargs="?", default=ROOT / "assets/original/CARDSHOP.EXE")
    parser.add_argument("--report", type=Path, help="Write the full structural report as JSON")
    parser.add_argument("--extract", type=Path, help="Extract numbered raw resources and segments into this folder")
    args = parser.parse_args()
    try:
        report = inspect_ne(args.file, args.extract)
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False))
        summary = {key: report[key] for key in ("file_name", "size_bytes", "sha256", "format", "expected_windows_version", "imports", "resource_counts", "resource_errors")}
        print(json.dumps(summary, indent=2))
    except (OSError, ValueError) as exc:
        print("Cannot inspect executable:", exc, file=sys.stderr)
        raise SystemExit(1)
