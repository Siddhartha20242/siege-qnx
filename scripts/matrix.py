#!/usr/bin/env python3
"""Run every attack scenario several times in one QNX boot and tabulate results.

    scripts/matrix.py [--runs 4] [--dur 5] [--deadline 15]

A scenario is "failed" in a run when the controller reports RESULT FAIL
(more than the tolerated share of late or lost frames, or a starved controller). Single runs are noisy under emulation, so
the failure *rate* is the number to look at.
"""
import argparse, os, re, socket, statistics, subprocess, sys, tempfile, time

SCENARIOS = [   # (label, ATK, ATK_PRIO, extra environment)
    ("baseline (no attacker)", "", 10, ""),
    ("cpu hog   @prio 10", "cpu", 10, ""),
    ("cpu hog   @prio 20", "cpu", 20, ""),
    ("flood     @prio 10", "flood", 10, ""),
    ("flood     @prio 20", "flood", 20, ""),
    ("workflood @prio 30", "workflood", 30, ""),
    ("mem hog   @prio 10", "mem", 10, ""),
    ("fd exhaust@prio 10", "fd", 10, ""),
    ("crash loop@prio 10", "crash", 10, ""),
    ("crash loop@prio 20", "crash", 20, ""),
    ("kill detector, no supervisor", "", 10, "KILL_AT=2"),
    ("kill detector, supervised", "", 10, "SUPERVISE=1 KILL_AT=2"),
]

ap = argparse.ArgumentParser()
ap.add_argument("--runs", type=int, default=4)
ap.add_argument("--dur", type=int, default=5)
ap.add_argument("--deadline", type=int, default=15)
ap.add_argument("--profile", default="none", help="none|prio|isolate|budget")
ap.add_argument("--json", default="", help="write every run to this JSON file")
ap.add_argument("--only", default="", help="substring filter on scenario labels")
ap.add_argument("--image", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "build", "siege.ifs"))
args = ap.parse_args()

sock_path = os.path.join(tempfile.mkdtemp(), "qnx.sock")
qemu = subprocess.Popen(
    ["qemu-system-aarch64", "-machine", "virt,gic-version=3", "-cpu", "cortex-a57",
     "-smp", "2", "-m", "512M", "-nographic", "-monitor", "none",
     "-serial", f"unix:{sock_path},server=on,wait=off", "-kernel", args.image],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

buf = ""
def pump(s):
    global buf
    try:
        d = s.recv(65536)
        if d:
            buf += d.decode(errors="replace")
    except socket.timeout:
        pass

def wait_for(s, pattern, timeout):
    """Wait until regex matches in buf[mark:]; return the new text."""
    global buf
    mark = len(buf)
    end = time.time() + timeout
    while time.time() < end:
        pump(s)
        if re.search(pattern, buf[mark:], re.M):
            return buf[mark:]
    return buf[mark:]

try:
    for _ in range(50):
        if os.path.exists(sock_path):
            break
        time.sleep(0.1)
    s = socket.socket(socket.AF_UNIX)
    s.connect(sock_path)
    s.settimeout(0.5)
    wait_for(s, r"Startup complete", 60)
    time.sleep(2)

    seq = 0
    def run(atk, prio, extra=""):
        global seq
        seq += 1
        s.send((f'PROFILE={args.profile} ATK="{atk}" ATK_PRIO={prio} {extra} DEADLINE_MS={args.deadline} '
                f'pipeline.sh {args.dur}; echo EN""D{seq}\n').encode())
        return wait_for(s, rf"^END{seq}", args.dur * 8 + 30)

    run("", 10)                                   # warm up the emulator, discard

    rows = []
    results_json = []
    for label, atk, prio, extra in SCENARIOS:
        if args.only and args.only not in label:
            continue
        res = []
        for _ in range(args.runs):
            out = run(atk, prio, extra)
            m = re.search(r"FINAL .*?late=(\d+) lost=(\d+) stalls=(\d+) p50_us=(\d+) p99_us=(\d+) max_us=(\d+)", out)
            if not m:
                res.append(None)
                continue
            late, lost, stalls, p50, p99, mx = map(int, m.groups())
            ex = re.search(r"outages=(\d+) outage_frames=(\d+) max_gap_ms=(\d+) abandoned=(\d)", out)
            rs = re.search(r"death_to_ready_ms=(\d+)", out)
            og = re.search(r"OUTAGE ms=(\d+)", out)
            res.append(dict(fail="RESULT FAIL" in out, late=late, lost=lost, stalls=stalls,
                            p50=p50, p99=p99, max=mx,
                            outages=int(ex.group(1)) if ex else 0,
                            max_gap_ms=int(ex.group(3)) if ex else 0,
                            abandoned=int(ex.group(4)) if ex else 0,
                            restart_ms=int(rs.group(1)) if rs else None,
                            outage_ms=int(og.group(1)) if og else None))
        rows.append((label, res))
        results_json.append(dict(profile=args.profile, scenario=label, atk=atk, atk_prio=prio, extra=extra, runs=res))
        ok = [r for r in res if r]
        print(f"{label:24} fail {sum(r['fail'] for r in ok)}/{len(res)}  "
              f"worst_max_ms={max((r['max'] for r in ok), default=0)/1000:.1f}  "
              f"median_p50_ms={statistics.median([r['p50'] for r in ok])/1000 if ok else 0:.1f}  "
              f"late_frames={sum(r['late'] for r in ok)}", flush=True)
finally:
    if args.json:
        import json
        json.dump(results_json, open(args.json, 'w'), indent=1)
    qemu.kill()
    qemu.wait()
