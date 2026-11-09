#!/usr/bin/env python3
"""Measure the confidence gate's advisory safe state on QNX: how often it triggers and how fast.

    python3 tools/measure_gate.py        # boots the image in QEMU; writes docs/results/safe-state.json

Three inputs, 8 runs each, DET_MODEL=cnn with SCORE_BAND set (the band from tools/eval_confidence.py, in the detector's units):
the synthetic camera, the real-photo scene (brightest pixel 140), and the hard scene (255, brighter than the object).
Written before the run: the first two should never enter the safe state (no unsure detections); the hard scene should.
"""
import json, os, re, sys
here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(here, "..", "scripts"))
from qnxconsole import Console

BAND = "37577:41532"
runs_per = 8
rows = {}
with Console(os.path.join(here, "..", "build", "siege.ifs")) as c:
    c.run("pipeline.sh 3 >/dev/null", 60)
    for label, env in (("synthetic camera", ""), ("real-photo scene (cap 140)", "SCENE=1 "), ("hard scene (cap 255)", "SCENE_HARD=1 ")):
        res = []
        for _ in range(runs_per):
            out = c.run(f"DET_MODEL=cnn SCORE_BAND={BAND} {env}pipeline.sh 8", 90)
            g = re.search(r"GATE band=\S+ flagged_wrong=(\d+) flagged_right=(\d+) silent_wrong=(\d+) safe_entries=(\d+) safe_frames=(\d+) mean_time_to_safe_ms=(\d+)", out)
            f = re.search(r"FINAL .*?frames=(\d+).*?checked=(\d+) wrong=(\d+)", out)
            ok = "RESULT PASS" in out
            res.append(dict(parsed=bool(g and f), frames=int(f.group(1)) if f else None, checked=int(f.group(2)) if f else None,
                            wrong=int(f.group(3)) if f else None, flagged_wrong=int(g.group(1)) if g else None,
                            flagged_right=int(g.group(2)) if g else None, silent_wrong=int(g.group(3)) if g else None,
                            safe_entries=int(g.group(4)) if g else None, safe_frames=int(g.group(5)) if g else None,
                            mean_time_to_safe_ms=int(g.group(6)) if g else None, verdict_pass=ok))
        rows[label] = res
        good = [r for r in res if r["parsed"]]
        print(f"{label}: {len(good)}/{runs_per} parsed; wrong {sum(r['wrong'] for r in good)} of {sum(r['checked'] for r in good)}; "
              f"flagged wrong {sum(r['flagged_wrong'] for r in good)}, flagged right {sum(r['flagged_right'] for r in good)}, "
              f"silent wrong {sum(r['silent_wrong'] for r in good)}; safe entries {sum(r['safe_entries'] for r in good)} "
              f"(runs with an entry: {sum(1 for r in good if r['safe_entries'])}); mean time to safe "
              f"{[r['mean_time_to_safe_ms'] for r in good if r['safe_entries']]} ms", flush=True)
json.dump(dict(band=BAND, runs_per_input=runs_per, results=rows), open(os.path.join(here, "..", "docs", "results", "safe-state.json"), "w"), indent=1)
