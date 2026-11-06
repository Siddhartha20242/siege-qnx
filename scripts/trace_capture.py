#!/usr/bin/env python3
"""Capture a QNX kernel trace of a flooded pipeline and summarise who used the CPU.

    scripts/trace_capture.py [--secs 1] [--out docs/trace-evidence.md]

Runs the `workflood` attack in the guest, records a kernel event trace with
`tracelogger` (the image's kernel, procnto-smp-instr, is the instrumented one),
carries the binary trace out over the serial console as base64 (`b64cat`), prints
it on the build machine with the x86-64 host `traceprinter`, and turns the thread
scheduling events into a CPU-share table per process.

What it can and cannot show: the printed events carry process and thread ids,
timestamps and message traffic, but no priorities, so the trace cannot confirm the
priority inheritance (`mechanism_proof.py` does that). It can measure how much CPU
each process really used, which tests the claim that the flooding attacker uses
almost none. The emulator workaround (the idle spinner) is switched off for the run,
so idle time shows up as idle.
"""
import argparse, base64, collections, os, re, subprocess, sys, time
here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, here)
from qnxconsole import Console

ap = argparse.ArgumentParser()
ap.add_argument("--secs", type=int, default=1)
ap.add_argument("--filter", type=int, default=1, help="tracelogger -F class to disable (1 = kernel calls)")
ap.add_argument("--kev", default=os.path.join(here, "..", "build", "siege.kev"))
ap.add_argument("--out", default=os.path.join(here, "..", "docs", "trace-evidence.md"))
ap.add_argument("--image", default=os.path.join(here, "..", "build", "siege.ifs"))
ap.add_argument("--vm", default=os.environ.get("SIEGE_VM") or open(os.path.join(here, "..", ".siege-vm")).read().strip())
args = ap.parse_args()

with Console(args.image) as c:
    c.run("pipeline.sh 3 >/dev/null", 60)
    cmd = ("on -p 61r ksh -c 'IDLE_POLL=0 ATK=workflood ATK_PRIO=30 DEADLINE_MS=20 pipeline.sh 5 >/dev/null & sleep 2; "
           f"tracelogger -s {args.secs} -F {args.filter} -f /dev/shmem/siege.kev; ls -l /dev/shmem/siege.kev; wait'")
    out = c.run(cmd, 90)
    print("\n".join(l for l in out.splitlines() if "siege.kev" in l or "racelogger" in l or "rror" in l)[:600])
    t = time.time()
    dump = c.run("b64cat /dev/shmem/siege.kev", 120)
    print(f"dump took {time.time()-t:.0f}s, {len(dump)} characters")

m = re.search(r"B64BEGIN\r?\n(.*?)B64END", dump, re.S)
if not m:
    sys.exit("no trace came out of the guest (no B64BEGIN/B64END)")
raw = base64.b64decode("".join(m.group(1).split()))
os.makedirs(os.path.dirname(os.path.abspath(args.kev)), exist_ok=True)
open(args.kev, "wb").write(raw)
print(f"wrote {args.kev}: {len(raw)} bytes")

subprocess.run(["scp", "-q", args.kev, f"{args.vm}:siege.kev"], check=True)
env = "source ~/qnx800/qnxsdp-env.sh >/dev/null 2>&1; "
subprocess.run(["ssh", args.vm, env + "traceprinter -f ~/siege.kev -o ~/siege.kev.txt >/dev/null 2>&1; "
                "traceprinter -v -f ~/siege.kev -o ~/siege.kev.v.txt >/dev/null 2>&1"], check=True, timeout=180)
txt = subprocess.run(["ssh", args.vm, "cat ~/siege.kev.txt"], capture_output=True, text=True, timeout=120).stdout
vtxt = subprocess.run(["ssh", args.vm, "cat ~/siege.kev.v.txt"], capture_output=True, text=True, timeout=120).stdout

# process names: PROCCREATE_NAME blocks in the verbose output
names = {}
for m in re.finditer(r"PROCCREATE_NAME\s+ppid:\d+\s+pid:(\d+)\s+name:(\S+)", vtxt):
    names[int(m.group(1))] = os.path.basename(m.group(2))
hz = int(re.search(r"TRACE_CYCLES_PER_SEC::\s*(\d+)", txt).group(1))

# per CPU, the running process is the one named by the latest THRUNNING event
last = {}                                    # cpu -> (t, pid)
busy = collections.Counter()
first_t, last_t = {}, {}
for m in re.finditer(r"t:0x([0-9a-f]+) CPU:(\d+) THREAD\s+:THRUNNING\s+pid:(\d+) tid:(\d+)", txt):
    t, cpu, pid = int(m.group(1), 16), int(m.group(2)), int(m.group(3))
    if cpu in last:
        busy[last[cpu][1]] += (t - last[cpu][0]) & 0xFFFFFFFF
    else:
        first_t[cpu] = t
    last[cpu] = (t, pid)
    last_t[cpu] = t
window = sum((last_t[c] - first_t[c]) & 0xFFFFFFFF for c in last_t)       # CPU-cycles observed, all CPUs
by_name = collections.Counter()
for pid, cyc in busy.items():
    nm = names.get(pid, f"pid {pid}")
    by_name["idle and kernel (procnto)" if nm.startswith("procnto") else nm] += cyc
rows = sorted(by_name.items(), key=lambda kv: -kv[1])
secs = window / hz
lines = ["# What the kernel trace shows: who used the CPU", "",
         f"A kernel trace of {args.secs} s taken 2 s into a run of the priority-30 `workflood` attack against the pipeline "
         f"(no hardening, `IDLE_POLL=0`), {len(raw)//1024} KB, {txt.count(chr(10))} printed events on {len(last)} CPUs. "
         f"The table attributes each CPU's time to the process named by its latest thread-running event.", "",
         f"Observed: {secs:.2f} CPU-seconds in total.", "", "| Process | Share of CPU time |", "|---|---|"]
for nm, cyc in rows:
    lines.append(f"| `{nm}` | {100 * cyc / window:.1f}% |")
atk = sum(c for nm, c in rows if nm == "attacker")
det = sum(c for nm, c in rows if nm == "detector")
lines += ["", f"The attacker used {100 * atk / window:.1f}% of the CPU time and the detector {100 * det / window:.1f}%. " +
          ("This supports the claim that the flooding attacker barely uses any CPU of its own: the damage is done through the "
           "detector's message queue." if atk / window < 0.1 else
           "The attacker used a noticeable share of the CPU, so the claim that it barely uses any does not hold in this trace."),
          "", "The trace also contains the message traffic: " +
          f"{len(re.findall(r':SND_MESSAGE', txt))} sends, {len(re.findall(r':REC_MESSAGE', txt))} receives and "
          f"{len(re.findall(r':REPLY_MESSAGE', txt))} replies in the window.",
          "", "Limits: a one-second window of one run; shares are from event timestamps and ignore time spent in interrupts; the printed "
          "events carry no priorities, so this trace does not show the priority inheritance itself (see `mechanism-proof.md`).", ""]
open(args.out, "w").write("\n".join(lines))
print("\n".join(lines))
