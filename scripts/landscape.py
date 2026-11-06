#!/usr/bin/env python3
"""Map the safe region: pipeline priority against attacker priority.

    scripts/landscape.py [--runs 2] [--dur 4]

For each pair (pipeline priority P, attacker priority A) it runs the attack and
records whether the pipeline kept its deadlines, for two attacks: a CPU hog and
the shared-service flood (`workflood`). It writes docs/landscape.md, one SVG heat
map per attack, and the raw runs as docs/landscape.json.

The point is the shape of the boundary, not any single cell: it shows how much
priority margin the pipeline needs, and whether equal priorities are safe.
"""
import argparse, json, os, re, sys
here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, here)
from qnxconsole import Console

ap = argparse.ArgumentParser()
ap.add_argument("--runs", type=int, default=2)
ap.add_argument("--dur", type=int, default=4)
ap.add_argument("--pipeline", default="5,10,15,20,30,40", help="pipeline priorities to try")
ap.add_argument("--attacker", default="10,20,30,40", help="attacker priorities to try")
ap.add_argument("--out", default=os.path.join(here, "..", "docs"))
ap.add_argument("--render-only", action="store_true", help="redraw docs/landscape.* from the saved landscape.json without running anything")
ap.add_argument("--image", default=os.path.join(here, "..", "build", "siege.ifs"))
args = ap.parse_args()

PIPE = [int(x) for x in args.pipeline.split(",")]
ATK = [int(x) for x in args.attacker.split(",")]
ATTACKS = [("cpu", "CPU hog"), ("workflood", "message flood to the shared detector")]
COL = {"ok": "#1a7f37", "warn": "#bf8700", "bad": "#cf222e"}

results = {}                                           # (attack, P, A) -> list of pass booleans
if args.render_only:
    for r in json.load(open(os.path.join(args.out, "landscape.json"))):
        results[(r["attack"], r["pipeline"], r["attacker"])] = r["passed"]
    PIPE = sorted({k[1] for k in results})
    ATK = sorted({k[2] for k in results})
    args.runs = len(next(iter(results.values())))
else:
    with Console(args.image) as c:
        c.run("pipeline.sh 3 >/dev/null", 60)
        for attack, _ in ATTACKS:
            for P in PIPE:
                for A in ATK:
                    passes = []
                    for _ in range(args.runs):
                        out = c.run(f'SRC_PRIO={P} DET_PRIO={P} CTL_PRIO={P} DEADLINE_MS=20 ATK="{attack}" ATK_PRIO={A} '
                                    f"pipeline.sh {args.dur}", args.dur * 8 + 30)
                        passes.append("RESULT PASS" in out)
                    results[(attack, P, A)] = passes
                    print(f"{attack:10} pipeline={P:2} attacker={A:2}: {sum(passes)}/{len(passes)} passed", flush=True)
    json.dump([dict(attack=a, pipeline=P, attacker=A, passed=p) for (a, P, A), p in results.items()],
              open(os.path.join(args.out, "landscape.json"), "w"), indent=1)


def svg(attack):
    cw, ch, lw, top = 90, 34, 120, 70
    w, h = lw + cw * len(ATK) + 20, top + ch * len(PIPE) + 30
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" font-family="system-ui,sans-serif" font-size="13">',
         f'<text x="{lw}" y="22" fill="#6e7781" font-weight="700">attacker priority</text>']
    for j, A in enumerate(ATK):
        o.append(f'<text x="{lw + cw*j + cw/2}" y="52" text-anchor="middle" fill="#6e7781">{A}</text>')
    o.append(f'<text x="6" y="{top - 6}" fill="#6e7781" font-weight="700">pipeline priority</text>')
    for i, P in enumerate(PIPE):
        y = top + ch * i
        o.append(f'<text x="{lw - 12}" y="{y + 22}" text-anchor="end" fill="#6e7781">{P}</text>')
        for j, A in enumerate(ATK):
            r = results[(attack, P, A)]
            k = sum(r)
            col = COL["ok"] if k == len(r) else (COL["bad"] if k == 0 else COL["warn"])
            o.append(f'<rect x="{lw + cw*j + 2}" y="{y + 2}" width="{cw - 4}" height="{ch - 4}" rx="4" fill="{col}"/>')
            o.append(f'<text x="{lw + cw*j + cw/2}" y="{y + 22}" text-anchor="middle" fill="#fff" font-weight="700">{k}/{len(r)} pass</text>')
    o.append("</svg>")
    return "\n".join(o)


def rule_check(attack):
    above = [(P, A) for P in PIPE for A in ATK if P > A]
    below = [(P, A) for P in PIPE for A in ATK if P < A]
    equal = [(P, A) for P in PIPE for A in ATK if P == A]
    cnt = lambda cells: (sum(sum(results[(attack, P, A)]) for P, A in cells), sum(len(results[(attack, P, A)]) for P, A in cells))
    return cnt(above), cnt(equal), cnt(below)


md = ["# Priority landscape", "",
      "How much priority does the pipeline need? Each cell is the pipeline configured at one priority (rows) against an",
      f"attacker at another (columns); {args.runs} runs of {args.dur} s each, 20 ms deadline. Green: every run passed.",
      "Red: none did. Amber: mixed. Measured in QEMU emulation, so read the shape, not single cells.", ""]
for attack, desc in ATTACKS:
    open(os.path.join(args.out, f"landscape-{attack}.svg"), "w").write(svg(attack) + "\n")
    (a_ok, a_n), (e_ok, e_n), (b_ok, b_n) = rule_check(attack)
    md += [f"## {desc}", "", f"![{desc}](landscape-{attack}.svg)", "",
           f"* Pipeline **above** the attacker: {a_ok} of {a_n} runs passed.",
           f"* Pipeline at the **same** priority: {e_ok} of {e_n} runs passed.",
           f"* Pipeline **below** the attacker: {b_ok} of {b_n} runs passed.", ""]
def verdict(ok, n):
    share = ok / n if n else 0
    return "safe" if share >= 0.9 else ("mostly safe" if share >= 0.5 else "not safe")


md += ["## What it shows", ""]
for attack, desc in ATTACKS:
    (a_ok, a_n), (e_ok, e_n), (b_ok, b_n) = rule_check(attack)
    md.append(f"* **{desc[0].upper() + desc[1:]}.** Above the attacker's priority the pipeline was {verdict(a_ok, a_n)} ({a_ok} of {a_n} runs); "
              f"at the same priority it was {verdict(e_ok, e_n)} ({e_ok} of {e_n}); below it, {verdict(b_ok, b_n)} ({b_ok} of {b_n}).")
(c_ok, c_n) = rule_check("cpu")[1]
(f_ok, f_n) = rule_check("workflood")[1]
md += ["",
       "**Note (added later):** a 15-run check of the reference pipeline at equal priority against a CPU hog failed 8 of 15 runs, "
       "and 11 of 15 in a repeat, so the equal-priority CPU cell below is unstable under emulation; see `more-attackers.md`.", "",
       "The boundary is where the pipeline's priority crosses the attacker's, and the **same-priority row is the interesting one**. "
       f"Against a CPU hog, equal priority is {verdict(c_ok, c_n)}, because round-robin scheduling shares the CPU between equals. "
       f"Against a flood of a shared service, equal priority is {verdict(f_ok, f_n)}. A likely reason, which these runs do not isolate: "
       "messages at one priority are served in the order they arrive, and a client that never stops sending is always ahead in the queue. So the margin the pipeline needs depends on "
       "the failure mode, and for a shared service the relevant priority is that of **every client of that service**, not only of "
       "processes that look like attackers.", ""]
open(os.path.join(args.out, "landscape.md"), "w").write("\n".join(md))
print("\n".join(md))
