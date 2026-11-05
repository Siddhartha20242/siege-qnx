#!/usr/bin/env python3
"""Run every scenario in siege.json several times in one QNX boot.

    scripts/matrix.py [--config siege.json] [--profile prio] [--runs 4] [--json out.json]

Scenarios and profiles are data: add an entry to siege.json to test a new
attack or fault. A run "fails" when the controller reports RESULT FAIL (more
than the tolerated share of late or lost frames, a silence longer than the
recovery budget, or a pipeline that never recovered). Single runs are noisy
under emulation, so the failure rate is the number to look at.
"""
import argparse, json, os, re, statistics, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from qnxconsole import Console

here = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser()
ap.add_argument("--config", default=os.path.join(here, "..", "siege.json"))
ap.add_argument("--profile", default="none")
ap.add_argument("--runs", type=int)
ap.add_argument("--dur", type=int)
ap.add_argument("--deadline", type=int)
ap.add_argument("--tolerance", type=int, help="tolerated late frames, per mille")
ap.add_argument("--json", default="", help="write every run to this JSON file")
ap.add_argument("--only", default="", help="substring filter on scenario labels")
ap.add_argument("--image", default=os.path.join(here, "..", "build", "siege.ifs"))
args = ap.parse_args()

cfg = json.load(open(args.config))
runs = args.runs or cfg.get("runs", 3)
dur = args.dur or cfg.get("duration_s", 5)
deadline = args.deadline or cfg.get("deadline_ms", 15)
tol = args.tolerance if args.tolerance is not None else cfg.get("tolerance_permille", 20)
recovery = cfg.get("recovery_ms", 500)

FINAL = re.compile(r"FINAL .*?late=(\d+) lost=(\d+) stalls=(\d+) p50_us=(\d+) p99_us=(\d+) max_us=(\d+)"
                   r"(?: outages=(\d+) outage_frames=(\d+) max_gap_ms=(\d+) abandoned=(\d))?")


def command(sc):
    env = {"PROFILE": args.profile, "ATK": sc.get("attacker", ""), "ATK_PRIO": sc.get("prio", 10),
           "DEADLINE_MS": deadline, "TOL_PM": tol, "RECOVERY_MS": recovery}
    env.update(sc.get("env", {}))
    parts = [f'{k}="{v}"' if k == "ATK" else f"{k}={v}" for k, v in env.items()]
    return " ".join(parts) + f" pipeline.sh {dur}"


results = []
with Console(args.image) as c:
    c.run("pipeline.sh 3 >/dev/null", 60)                       # warm up, discard
    for sc in cfg["scenarios"]:
        if args.only and args.only not in sc["label"]:
            continue
        res = []
        for _ in range(runs):
            out = c.run(command(sc), dur * 8 + 30)
            m = FINAL.search(out)
            if not m:
                res.append(None)
                continue
            late, lost, stalls, p50, p99, mx, outages, _of, gap, aband = m.groups()
            rs = re.search(r"death_to_ready_ms=(\d+)", out)
            og = re.search(r"OUTAGE ms=(\d+)", out)
            res.append(dict(fail="RESULT FAIL" in out, late=int(late), lost=int(lost), stalls=int(stalls),
                            p50=int(p50), p99=int(p99), max=int(mx),
                            outages=int(outages or 0), max_gap_ms=int(gap or 0), abandoned=int(aband or 0),
                            restart_ms=int(rs.group(1)) if rs else None,
                            outage_ms=int(og.group(1)) if og else None))
        ok = [r for r in res if r]
        results.append(dict(profile=args.profile, scenario=sc["label"], atk=sc.get("attacker", ""),
                            atk_prio=sc.get("prio", 10), extra=sc.get("env", {}), runs=res))
        print(f"{sc['label']:30} fail {sum(r['fail'] for r in ok)}/{len(res)}  "
              f"worst_max_ms={max((r['max'] for r in ok), default=0)/1000:.1f}  "
              f"median_p50_ms={statistics.median([r['p50'] for r in ok])/1000 if ok else 0:.1f}  "
              f"late_frames={sum(r['late'] for r in ok)}", flush=True)

if args.json:
    json.dump(results, open(args.json, "w"), indent=1)
