#!/usr/bin/env python3
"""Find the abilities the detector's security type really needs, by measurement.

    python3 tools/minimize_policy.py probe     write image/secpol-probe/: the open policy with ONE ability removed
                                               from det_t per file (then run ./siege build)
    python3 tools/minimize_policy.py run       boot the image, run the pipeline under each probe policy, record
                                               which abilities it survives without
    python3 tools/minimize_policy.py combine   keep the abilities that were needed, write tools/det_least.txt

An ability is called removable only if the pipeline passes, with a detector killed and restarted by its
supervisor mid-run, in every trial without it. That run exercises starting, naming, scheduling and
restarting a process, so an ability it never uses is one this pipeline does not need. Anything that
failed, or that the compiler refused to build, is kept. The result is a policy that is
tight for what we tried and says nothing about code paths we did not run.
"""
import json, os, re, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gen_secpol import ABILITIES, PROBE_OUT, LEAST_FILE, policy

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
OUT = os.path.join(ROOT, "docs", "results", "secpol-minimize.json")
TRIALS = 2
CMD = "SUPERVISE=1 KILL_AT=2 PROFILE=secpol-{name} pipeline.sh 5"


def probe():
    os.makedirs(PROBE_OUT, exist_ok=True)
    for f in os.listdir(PROBE_OUT):
        os.remove(os.path.join(PROBE_OUT, f))
    for a in ABILITIES:
        with open(os.path.join(PROBE_OUT, f"probe-{a}.secpol"), "w") as f:
            f.write(policy(f"probe-{a}", det_drop=(a,)))
    print(f"wrote {len(ABILITIES)} probe policies to image/secpol-probe/. Now: ./siege build")


def run(image):
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    from qnxconsole import Console
    results, t0 = {}, time.time()
    names = ["open"] + [f"probe-{a}" for a in ABILITIES]          # `open` first, as the control
    with Console(image) as c:
        c.run("pipeline.sh 3 >/dev/null", 60)
        for i, name in enumerate(names):
            if i and i % 12 == 0:                                    # fresh guest now and then (docs/more-attackers.md)
                c.close(); c.__init__(image); c.run("pipeline.sh 3 >/dev/null", 60)
            built = "secpol-%s.bin" % name in c.run(f"ls /proc/boot/secpol-{name}.bin 2>&1; true", 10)
            if not built:
                results[name] = dict(built=False, passes=0, trials=0)
                print(f"{name:28} not in the image (the compiler refused it)", flush=True)
                continue
            passes = 0
            for _ in range(TRIALS if name != "open" else 4):
                out = c.run(CMD.format(name=name), 60)
                passes += "RESULT PASS" in out and "failed" not in out.split("RESULT")[0].split("RUN profile")[-1]
            n = TRIALS if name != "open" else 4
            results[name] = dict(built=True, passes=passes, trials=n)
            print(f"{name:28} {passes}/{n} passed", flush=True)
    json.dump(dict(trials=TRIALS, minutes=round((time.time() - t0) / 60, 1), results=results), open(OUT, "w"), indent=1)
    print("wrote", os.path.normpath(OUT))


def combine():
    d = json.load(open(OUT))["results"]
    removable = [a for a in ABILITIES if d.get(f"probe-{a}", {}).get("built") and d[f"probe-{a}"]["passes"] == d[f"probe-{a}"]["trials"]]
    kept = [a for a in ABILITIES if a not in removable]
    with open(LEAST_FILE, "w") as f:
        f.write("# Abilities det_t keeps in the `least` policy. Written by tools/minimize_policy.py combine.\n")
        f.write("\n".join(kept) + "\n")
    print(f"{len(removable)} of {len(ABILITIES)} abilities were not needed; det_t keeps {len(kept)}: {' '.join(kept)}")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "probe":
        probe()
    elif mode == "run":
        run(os.path.join(ROOT, "build", "siege.ifs"))
    elif mode == "combine":
        combine()
    else:
        sys.exit(__doc__)
