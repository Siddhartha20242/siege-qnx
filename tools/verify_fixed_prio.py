#!/usr/bin/env python3
"""Check that DET_FIXED_PRIO=1 really stops the detector taking its client's priority, before trusting the control.

    python3 tools/verify_fixed_prio.py        # boots the image in QEMU; writes docs/results/fixed-prio-check.json

Samples the detector's real priority with `pidin` ten times during a priority-30 `workflood`, with and without the flag.
If the flag works, the detector should stay at 10; without it, the earlier run saw it at 30 in 36 of 44 samples.
"""
import json, os, re, sys, collections
here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(here, "..", "scripts"))
from qnxconsole import Console

out = {}
with Console(os.path.join(here, "..", "build", "siege.ifs")) as c:
    c.run("pipeline.sh 3 >/dev/null", 60)
    for label, flag in (("without the flag", ""), ("DET_FIXED_PRIO=1", "DET_FIXED_PRIO=1 ")):
        counts = collections.Counter()
        for _ in range(3):
            text = c.run(f"{flag}ATK=workflood ATK_PRIO=30 DEADLINE_MS=20 pipeline.sh 8 >/dev/null & sleep 2; "
                         "i=0; while [ $i -lt 10 ]; do pidin -f anp | grep -E ' proc/boot/detector'; sleep 0.3; i=$((i+1)); done; wait", 90)
            for line in text.splitlines():
                m = re.search(r"proc/boot/detector\s+(\d+)r?\s*$", line.strip())
                if m:
                    counts[int(m.group(1))] += 1
        out[label] = dict(counts)
        print(f"{label}: detector priority samples {dict(counts)}", flush=True)
json.dump(out, open(os.path.join(here, "..", "docs", "results", "fixed-prio-check.json"), "w"), indent=1)
