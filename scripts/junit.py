#!/usr/bin/env python3
"""Turn matrix.py results into JUnit XML and a pass/fail exit code, for CI.

    scripts/junit.py res-prio.json [more.json ...] [--out junit.xml]

Each (profile, scenario) becomes one test case. A scenario can say what it is
expected to do under each profile in siege.json:

    {"label": "workflood @prio 30", "attacker": "workflood", "prio": 30,
     "expect": {"none": "fail", "isolate": "fail", "budget": "fail"}}

The default expectation is "pass". A case is observed as "pass" when at most
--max-fail-rate of its runs failed (default 0.2), otherwise "fail". The case
passes when the observation matches the expectation, so a regression (an
expected pass that now fails) and an unexpected fix both break the build and
get a human to look. Exit code: 0 if every case matched, 1 otherwise.
"""
import argparse, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from siegelib import observed_verdict
from xml.sax.saxutils import escape, quoteattr

here = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser()
ap.add_argument("files", nargs="+")
ap.add_argument("--config", default=os.path.join(here, "..", "siege.json"))
ap.add_argument("--out", default="junit.xml")
ap.add_argument("--max-fail-rate", type=float, default=0.2)
ap.add_argument("--only-profile", action="append", default=[], help="report only these profiles")
args = ap.parse_args()

expect = {}
if os.path.exists(args.config):
    for sc in json.load(open(args.config)).get("scenarios", []):
        expect[sc["label"]] = sc.get("expect", {})

rows = []
for f in args.files:
    rows += json.load(open(f))
rows = [r for r in rows if not args.only_profile or r["profile"] in args.only_profile]

best = {}                                    # same (profile, scenario) in several files: keep the one with more runs
for r in rows:
    k = (r["profile"], r["scenario"])
    if k not in best or len(r["runs"]) > len(best[k]["runs"]):
        best[k] = r
rows = list(best.values())

suites = {}
mismatches = 0
for r in rows:
    runs = [x for x in r["runs"] if x]
    n = len(r["runs"])
    fails = sum(1 for x in runs if x["fail"])
    observed = observed_verdict(fails, n, args.max_fail_rate)
    wanted = expect.get(r["scenario"], {}).get(r["profile"], "pass")
    ok = observed == wanted
    worst = max((x["max"] for x in runs), default=0)
    detail = f"{fails}/{n} runs failed, worst frame {worst/1000:.1f} ms"
    suites.setdefault(r["profile"], []).append((r["scenario"].strip(), ok, wanted, observed, detail))
    if not ok:
        mismatches += 1

out = ['<?xml version="1.0" encoding="UTF-8"?>', "<testsuites>"]
for profile, cases in suites.items():
    bad = sum(1 for c in cases if not c[1])
    out.append(f'  <testsuite name="siege-{escape(profile)}" tests="{len(cases)}" failures="{bad}">')
    for name, ok, wanted, observed, detail in cases:
        out.append(f'    <testcase classname="siege.{escape(profile)}" name={quoteattr(name)}>')
        if not ok:
            msg = f"expected {wanted.upper()} but observed {observed.upper()} ({detail})"
            out.append(f"      <failure message={quoteattr(msg)}>{escape(msg)}</failure>")
        else:
            out.append(f"      <system-out>{escape(f'{observed.upper()} as expected: {detail}')}</system-out>")
        out.append("    </testcase>")
    out.append("  </testsuite>")
out.append("</testsuites>")
open(args.out, "w").write("\n".join(out) + "\n")

total = sum(len(c) for c in suites.values())
print(f"{total - mismatches}/{total} cases matched their expectation; wrote {args.out}")
for profile, cases in suites.items():
    for name, ok, wanted, observed, detail in cases:
        if not ok:
            print(f"  MISMATCH [{profile}] {name}: expected {wanted.upper()}, observed {observed.upper()} ({detail})")
sys.exit(1 if mismatches else 0)
