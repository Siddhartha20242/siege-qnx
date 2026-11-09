#!/usr/bin/env python3
"""Check three claims a reviewer questioned, on the QNX image in QEMU. Writes docs/results/verified-claims.json.

    python3 tools/verify_claims.py

1. Under the `fortress` profile, do the detector, camera, controller and supervisor really run at the priorities the profile asks for,
   although their security types hold no abilities?
2. Does `TraceEvent` work from the controller when its type (lockdown) holds no abilities?
3. Do reply timeouts fire against a squatter that never replies? Compares the camera's `dropped` count with what a working
   timeout would give.
"""
import json, os, re, sys
here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(here, "..", "scripts"))
from qnxconsole import Console

res = {}
with Console(os.path.join(here, "..", "build", "siege.ifs")) as c:
    c.run("pipeline.sh 3 >/dev/null", 60)

    # 1. priorities under fortress
    out = c.run("PROFILE=fortress SUPERVISE=1 pipeline.sh 8 >/dev/null & sleep 3; pidin -f anp | grep -E 'proc/boot/(supervisor|detector|controller|frame_src)'; wait", 90)
    prios = {}
    for line in out.splitlines():
        m = re.search(r"proc/boot/(supervisor|detector|controller|frame_src)\s+(\d+)r?\s*$", line.strip())
        if m:
            prios[m.group(1)] = int(m.group(2))
    res["fortress_priorities_asked_40_40_40_supervisor_50"] = prios
    print("fortress priorities:", prios, flush=True)

    # 2. TraceEvent under the lockdown types (a detector kill with no supervisor forces stalls, which write marks)
    out = c.run("PROFILE=secpol-lockdown SIEGE_TRACE=1 KILL_AT=2 pipeline.sh 6", 90)
    failed = [l for l in out.splitlines() if "TRACE user event failed" in l]
    res["traceevent_under_lockdown"] = dict(error_lines=failed[:2], stalls_seen=bool(re.search(r"stalls=([1-9]\d*)", out)))
    print("TraceEvent under lockdown:", res["traceevent_under_lockdown"], flush=True)

    # 3. reply timeout against the squatter
    runs = []
    for _ in range(3):
        out = c.run("ATK=squat ATK_PRIO=20 SUPERVISE=1 KILL_AT=2 pipeline.sh 6", 90)
        m = re.search(r"SRC frames=(\d+) sent=(\d+) dropped=(\d+)", out)
        a = re.search(r"ATK mode=squat.*", out)
        runs.append(dict(src=m.groups() if m else None, atk=a.group(0) if a else None))
    res["squat_reply_timeout"] = runs
    print("squat reply timeout:", runs, flush=True)
json.dump(res, open(os.path.join(here, "..", "docs", "results", "verified-claims.json"), "w"), indent=1)
