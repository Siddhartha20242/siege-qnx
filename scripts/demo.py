#!/usr/bin/env python3
"""Scripted demo: boots Siege on QNX in QEMU and plays the scenes in order.

    scripts/demo.py                  # all scenes, typed at a readable speed
    scripts/demo.py --speed 0        # no typing delay
    scripts/demo.py --scene hog      # one scene (names below)

The output is the real QNX serial console. Lines starting with '#' are the
host narrating; everything else comes from the guest. Meant for a screen
recording, so every scene is deterministic and short.
"""
import argparse, os, re, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from qnxconsole import Console

here = os.path.dirname(os.path.abspath(__file__))
B, RED, GRN, YEL, CYA, DIM, RST = "\033[1m", "\033[31m", "\033[32m", "\033[33m", "\033[36m", "\033[2m", "\033[0m"

SCENES = [
    ("intro", "Siege runs a camera -> detector -> controller pipeline on QNX 8.0 (aarch64, in QEMU).",
     [("uname -a", None)]),
    ("clean", "A clean run: every frame meets its 20 ms deadline.",
     [("pipeline.sh 5", None)]),
    ("hog", "RED: a priority-20 CPU hog against the priority-10 pipeline. No hardening.",
     [("ATK=cpu ATK_PRIO=20 pipeline.sh 5", None)]),
    ("hogfix", "GREEN: the same attack, with the attacker capped by QNX SCHED_SPORADIC.",
     [("PROFILE=budget ATK=cpu ATK_PRIO=20 pipeline.sh 5", None)]),
    ("flood", "A non-obvious attack: a priority-30 flood of expensive requests. It barely uses any CPU.",
     [("ATK=workflood ATK_PRIO=30 pipeline.sh 5", None)]),
    ("floodisolate", "Giving the pipeline its own CPU does not help. The damage is in the shared detector's queue.",
     [("PROFILE=isolate ATK=workflood ATK_PRIO=30 pipeline.sh 5", None)]),
    ("floodfix", "Raising the pipeline's priority fixes it.",
     [("PROFILE=prio ATK=workflood ATK_PRIO=30 pipeline.sh 5", None)]),
    ("status", "Live status from our resource manager, /dev/siege, while a run is going.",
     [("pipeline.sh 6 > /dev/null & sleep 4; cat /dev/siege; wait", None)]),
    ("kill", "Fault injection: kill the detector two seconds in, with no supervisor.",
     [("KILL_AT=2 pipeline.sh 6", None)]),
    ("killfix", "Now with the supervisor: it restarts the detector and measures the recovery.",
     [("SUPERVISE=1 KILL_AT=2 pipeline.sh 6", None)]),
]

HIDE = re.compile(r'^(PRIO |FINAL |.*EN""D|END\d+)')


def paint(line):
    if "RESULT PASS" in line or "state=GREEN" in line: return GRN + line + RST
    if "RESULT FAIL" in line or "state=RED" in line: return RED + line + RST
    if line.startswith(("SUP", "OUTAGE")): return CYA + line + RST
    if line.startswith("SUMMARY"): return DIM + line + RST
    if line.startswith("ATK"): return YEL + line + RST
    return line


class Demo:
    def __init__(self, image, speed, show_final):
        self.c = Console(image)
        self.speed = speed
        self.show_final = show_final

    def narrate(self, text):
        print(f"\n{B}# {text}{RST}", flush=True)
        time.sleep(1.2 if self.speed else 0)

    def run(self, cmd, timeout=90):
        print(f"{B}${RST} ", end="", flush=True)
        for ch in cmd:                                   # typed on screen, sent in one go
            print(ch, end="", flush=True)
            time.sleep(self.speed)
        print(flush=True)

        c = self.c
        c.seq += 1
        marker = f"END{c.seq}"
        c.sock.send((f'{cmd}; echo EN""D{c.seq}\n').encode())
        pending, mark, end = "", len(c.buf), time.time() + timeout
        shown = 0
        while time.time() < end:
            c._pump()
            pending = c.buf[mark:]
            lines = pending.split("\n")
            complete = lines[:-1]
            while shown < len(complete):
                line = complete[shown].rstrip("\r")
                shown += 1
                if re.match(rf"^{marker}", line):
                    return
                if HIDE.match(line) and not (self.show_final and line.startswith("FINAL")):
                    continue
                if line.strip() in ("#", ""):
                    continue
                print(paint(line), flush=True)

    def close(self):
        self.c.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--speed", type=float, default=0.025, help="seconds per typed character (0 = instant)")
    ap.add_argument("--scene", action="append", help="run only these scenes: " + ", ".join(s[0] for s in SCENES))
    ap.add_argument("--final", action="store_true", help="also show the FINAL summary line of each run")
    ap.add_argument("--image", default=os.path.join(here, "..", "build", "siege.ifs"))
    args = ap.parse_args()

    demo = Demo(args.image, args.speed, args.final)
    try:
        demo.c.run("pipeline.sh 3 >/dev/null", 60)       # warm the emulator, unseen
        for name, text, cmds in SCENES:
            if args.scene and name not in args.scene:
                continue
            demo.narrate(text)
            for cmd, timeout in cmds:
                demo.run(cmd, timeout or 90)
            time.sleep(1.5 if args.speed else 0)
    finally:
        demo.close()


if __name__ == "__main__":
    main()
