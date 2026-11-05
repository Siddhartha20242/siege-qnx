#!/usr/bin/env python3
"""Measure the emulator's own noise with no attacker and recommend a deadline.

    scripts/calibrate.py [--runs 15] [--dur 5] [--out calibration.json]

A deadline that sits inside the baseline noise makes every verdict a coin
flip. This runs the clean pipeline repeatedly with a deadline far above any
latency, looks at the worst frame of each run, and recommends a deadline with
headroom over the worst of them.
"""
import argparse, json, math, os, re, statistics, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from qnxconsole import Console

ap = argparse.ArgumentParser()
ap.add_argument("--runs", type=int, default=15)
ap.add_argument("--dur", type=int, default=5)
ap.add_argument("--headroom", type=float, default=1.5, help="deadline = worst run max x headroom")
ap.add_argument("--out", default="calibration.json")
ap.add_argument("--image", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "build", "siege.ifs"))
args = ap.parse_args()

maxes, p99s, p50s = [], [], []
with Console(args.image) as c:
    c.run("pipeline.sh 3 >/dev/null", 60)                     # warm up, discard
    for i in range(args.runs):
        out = c.run(f"DEADLINE_MS=1000 pipeline.sh {args.dur}", args.dur * 8 + 30)
        m = re.search(r"FINAL .*?p50_us=(\d+) p99_us=(\d+) max_us=(\d+)", out)
        if m:
            p50, p99, mx = map(int, m.groups())
            p50s.append(p50); p99s.append(p99); maxes.append(mx)
            print(f"run {i+1:2d}: p50 {p50/1000:5.1f} ms  p99 {p99/1000:5.1f} ms  max {mx/1000:5.1f} ms", flush=True)

if not maxes:
    sys.exit("no usable runs")

worst = max(maxes)
ordered = sorted(maxes)
p95 = ordered[min(len(ordered) - 1, math.ceil(0.95 * len(ordered)) - 1)]
deadline = max(10, int(math.ceil(worst * args.headroom / 1000.0 / 5.0) * 5))
result = dict(runs=len(maxes), median_p50_ms=round(statistics.median(p50s) / 1000, 2),
              median_p99_ms=round(statistics.median(p99s) / 1000, 2),
              run_max_p95_ms=round(p95 / 1000, 2), run_max_worst_ms=round(worst / 1000, 2),
              headroom=args.headroom, deadline_ms=deadline, tolerance_permille=20)
json.dump(result, open(args.out, "w"), indent=1)
print()
print(f"noise floor: median p50 {result['median_p50_ms']} ms, worst frame in any run {result['run_max_p95_ms']} ms (p95) / {result['run_max_worst_ms']} ms (max)")
print(f"recommended deadline: {deadline} ms (worst run x {args.headroom}, rounded up to 5 ms); tolerance 2.0%")
print(f"wrote {args.out}")
