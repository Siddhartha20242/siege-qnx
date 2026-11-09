#!/usr/bin/env python3
"""Does host load on the Mac cause unparsed or failed runs? Tests the hypothesis behind docs/fortress.md.

    python3 tools/host_contention_test.py        # boots the image in QEMU; writes docs/results/host-contention.json

Runs the same `fortress` scenario 20 times with the host idle and 20 times while one busy-loop process per CPU core
runs on the Mac, and counts runs with no parsable FINAL line and runs that failed. The busy-loop processes are started and
stopped by this script (it kills only the ones it started).
"""
import json, os, re, subprocess, sys, time
here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(here, "..", "scripts"))
from qnxconsole import Console
import siegelib as L

FINAL = re.compile(r"FINAL .*?late=(\d+) lost=(\d+) stalls=(\d+) p50_us=(\d+) p99_us=(\d+) max_us=(\d+)")
cfg = json.load(open(os.path.join(here, "..", "examples", "fortress", "siege.json")))
sc = [s for s in cfg["scenarios"] if s["label"] == "name squat, race after restart"][0]
cmd = L.build_command(cfg, sc, "fortress", 5, deadline=20, tol=20, recovery=500)
RUNS = 20


def burn(n):
    return [subprocess.Popen(["yes"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) for _ in range(n)]


def measure(c, label):
    unparsed = fails = 0
    tails = []
    for _ in range(RUNS):
        out = c.run(cmd, 70)
        if not FINAL.search(out):
            unparsed += 1
            tails.append(out[-400:])
        elif "RESULT FAIL" in out:
            fails += 1
    print(f"{label}: {RUNS} runs, {unparsed} unparsed, {fails} failed", flush=True)
    return dict(runs=RUNS, unparsed=unparsed, failed=fails, tails=tails[:2])


res = {}
ncpu = os.cpu_count() or 4
with Console(os.path.join(here, "..", "build", "siege.ifs")) as c:
    c.run("pipeline.sh 3 >/dev/null", 60)
    res["host idle"] = measure(c, "host idle")
    procs = burn(ncpu)
    try:
        time.sleep(3)
        res[f"host saturated ({ncpu} busy-loop processes)"] = measure(c, f"host saturated ({ncpu} busy loops)")
    finally:
        for p in procs:
            p.kill()
            p.wait()
json.dump(res, open(os.path.join(here, "..", "docs", "results", "host-contention.json"), "w"), indent=1)
