#!/usr/bin/env python3
"""Print the result files in the order the report tools should read them (later files win).

    ./siege report $(python3 scripts/results_files.py) --out docs/report

The files differ in how many runs they have, and the report keeps the last file that has a
given scenario. The order is oldest and thinnest first, then the 15-run files, then the
re-runs that replaced rows of the full matrix (see docs/more-attackers.md). Files that are
not scenario results (search, predictor, timelines, repeats) are left out.
"""
import glob, os
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "results")
ORDER = ["res", "deep", "inv", "new", "new5", "deep2", "deep3", "full", "rerun", "squat"]
files = []
for prefix in ORDER:
    files += sorted(glob.glob(os.path.join(ROOT, f"{prefix}-*.json")))
print(" ".join(os.path.normpath(f) for f in files))
