#!/usr/bin/env python3
"""Validate and prepare the supplied assets; optional Inkscape reference playback.

This is a developer/import tool. The distributed GUI uses the prepared images
and does not invoke Inkscape or access the internet at runtime.
"""
from __future__ import annotations

from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PIL import Image
from opencardshop.assets import AssetStore
from opencardshop.formats import expand_szdd, read_wmf, read_cmk
from opencardshop.wmf import render_wmf


def prepare(root: Path, destination: Path, reference: bool = False, workers: int = 4):
    destination.mkdir(parents=True, exist_ok=True)
    store = AssetStore(root, rendered=destination)
    failures, artwork = [], []
    executable = shutil.which("inkscape") if reference else None
    if reference and not executable:
        raise RuntimeError("--inkscape requires the Inkscape executable")

    def convert(file: Path):
        entry = {"name": file.name.upper(), "sha256": hashlib.sha256(file.read_bytes()).hexdigest()}
        target = destination / (file.stem.upper() + ".png")
        try:
            data = expand_szdd(file.read_bytes())
            mf = read_wmf(data)
            w, h = mf.bounds[2] - mf.bounds[0], mf.bounds[3] - mf.bounds[1]
            scale = min(0.3, 2400 / max(w, h))
            width, height = max(1, round(w * scale)), max(1, round(h * scale))
            if executable:
                with tempfile.TemporaryDirectory(prefix="opencardshop-") as temp:
                    input_path = Path(temp) / (file.stem + ".wmf")
                    input_path.write_bytes(data)
                    svg = destination / (file.stem.upper() + ".svg")
                    for args in (["--export-type=svg", "--export-plain-svg", "--export-filename=" + str(svg)],
                                 ["--export-width=" + str(width), "--export-background-opacity=0", "--export-filename=" + str(target)]):
                        result = subprocess.run([executable, str(input_path), *args], capture_output=True, timeout=40)
                        if result.returncode:
                            raise RuntimeError(result.stderr.decode(errors="replace")[-500:])
            else:
                render_wmf(data, (width, height), store.font).save(target)
            with Image.open(target) as image:
                image.load()
                entry["pixels"] = list(image.size)
            entry["status"] = "vector"
            entry["renderer"] = "Inkscape" if executable else "Pillow WMF subset"
        except Exception as exc:
            entry["reason"] = str(exc)
            bitmap = store.bitmaps.get(file.stem.upper())
            if bitmap:
                with Image.open(bitmap) as image:
                    image.convert("RGBA").save(target)
                    entry["pixels"] = list(image.size)
                entry["status"] = "bitmap_fallback"
            else:
                entry["status"] = "unavailable"
                if target.exists():
                    target.unlink()
        return entry

    paths = sorted(store.art_files.values(), key=lambda p: p.name.upper())
    with ThreadPoolExecutor(max_workers=max(1, min(8, workers))) as pool:
        for i, entry in enumerate(pool.map(convert, paths), 1):
            artwork.append(entry)
            if i % 100 == 0 or i == len(paths):
                print(f"Prepared {i}/{len(paths)} graphics", flush=True)
    cards = []
    for path in sorted(root.rglob("*")):
        if path.suffix.upper() != ".CMK":
            continue
        try:
            card = read_cmk(path)
            cards.append({"path": str(path.relative_to(root)), "fold": card.fold,
                          "panels": {s: len(v) for s, v in card.panels.items()},
                          "variant": "1.20" if card.header_flags is not None else "original"})
        except Exception as exc:
            failures.append({"path": str(path.relative_to(root)), "reason": str(exc)})
    report = {"artwork": artwork, "cards": cards, "card_errors": failures,
              "summary": {"artwork_files": len(paths), "vector": sum(a["status"] == "vector" for a in artwork),
                          "bitmap_fallback": sum(a["status"] == "bitmap_fallback" for a in artwork),
                          "unavailable": sum(a["status"] == "unavailable" for a in artwork),
                          "cards": len(cards), "card_errors": len(failures)}}
    (destination / "asset_report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report["summary"], indent=2))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "assets" / "original")
    parser.add_argument("--output", type=Path, default=ROOT / "assets" / "rendered")
    parser.add_argument("--inkscape", action="store_true", help="use Inkscape as a reference renderer; preserve SVGs")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    prepare(args.source.resolve(), args.output.resolve(), args.inkscape, args.workers)
