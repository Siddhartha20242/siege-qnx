#!/usr/bin/env python3
"""Search for attack combinations that break the pipeline, then shrink each to its core.

    ./siege search [--trials 30] [--seed 1] [--profile none] [--prios 5,10] [--out docs/search.md]

The scenarios in siege.json are ones a person thought of. This samples combinations
of attackers at random (one to three at once, at one priority), runs each in the
guest, and keeps those that fail every time they are tried. Each failure is then
shrunk: attackers are removed one at a time, and the priority lowered, while it
still fails. The result is a minimal reproduction.

A shrunk case with two or more attackers is checked once more: each attacker alone
is run at the same priority. If every one of them passes alone, the failure is an
interaction, something no single-attack scenario would have found. Failures made of
one attacker that breaks the pipeline alone (a CPU hog above its priority, say) are
reported too, but they are the known patterns and are labelled so.

Same seed, same sequence of trials. Emulator noise still applies, so a failure must
repeat in all of --confirm runs before it counts.
"""
import argparse, json, os, random, sys, time
here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, here)
from qnxconsole import Console

ATTACKERS = ["cpu", "ai", "mem", "flood", "workflood", "fd", "crash", "pipeflood", "membw", "timerstorm", "kcall"]

ap = argparse.ArgumentParser()
ap.add_argument("--trials", type=int, default=30, help="random combinations to try")
ap.add_argument("--seed", type=int, default=1)
ap.add_argument("--profile", default="none")
ap.add_argument("--prios", default="5,10", help="attacker priorities to sample (the pipeline runs at 10)")
ap.add_argument("--confirm", type=int, default=2, help="runs per check; a failure must repeat in all of them")
ap.add_argument("--dur", type=int, default=4)
ap.add_argument("--deadline", type=int, default=20)
ap.add_argument("--max-attackers", type=int, default=3)
ap.add_argument("--out", default=os.path.join(here, "..", "docs", "search.md"))
ap.add_argument("--json", default=os.path.join(here, "..", "docs", "results", "search.json"))
ap.add_argument("--image", default=os.path.join(here, "..", "build", "siege.ifs"))
args = ap.parse_args()

rng = random.Random(args.seed)
PRIOS = [int(x) for x in args.prios.split(",")]
cache = {}
log = []


def fails(c, attackers, prio):
    """True if the pipeline failed in every one of --confirm runs. Cached."""
    key = (tuple(sorted(attackers)), prio)
    if key not in cache:
        res = []
        for _ in range(args.confirm):
            out = c.run(f'PROFILE={args.profile} DEADLINE_MS={args.deadline} ATK="{" ".join(key[0])}" ATK_PRIO={prio} '
                        f"pipeline.sh {args.dur}", args.dur * 8 + 30)
            res.append("RESULT FAIL" in out)
            if not res[-1]:
                break                      # one pass is enough to say it is not a reliable failure
        cache[key] = len(res) == args.confirm and all(res)
        log.append(dict(attackers=list(key[0]), prio=prio, failed=cache[key]))
        print(f"  {'FAIL' if cache[key] else 'ok  '}  {' + '.join(key[0]):40} prio {prio}", flush=True)
    return cache[key]


def shrink(c, attackers, prio):
    attackers = list(attackers)
    changed = True
    while changed and len(attackers) > 1:
        changed = False
        for a in list(attackers):
            rest = [x for x in attackers if x != a]
            if rest and fails(c, rest, prio):
                attackers, changed = rest, True
                break
    for lower in sorted(p for p in PRIOS if p < prio):          # lowest priority that still fails
        if fails(c, attackers, lower):
            return attackers, lower
    return attackers, prio


found = {}
t0 = time.time()
with Console(args.image) as c:
    c.run("pipeline.sh 3 >/dev/null", 60)
    for t in range(args.trials):
        k = rng.randint(1, args.max_attackers)
        combo = rng.sample(ATTACKERS, k)
        prio = rng.choice(PRIOS)
        print(f"trial {t + 1}/{args.trials}", flush=True)
        if fails(c, combo, prio):
            core, p = shrink(c, combo, prio)
            found[(tuple(sorted(core)), p)] = combo
    cores = []
    for (core, p), origin in found.items():
        singles = {a: fails(c, [a], p) for a in core} if len(core) > 1 else {}
        cores.append(dict(attackers=list(core), prio=p, found_in=origin,
                          kind="known pattern (one attacker breaks it alone)" if len(core) == 1
                          else ("interaction (each alone passes)" if not any(singles.values())
                                else "contains an attacker that breaks it alone"),
                          singles=singles))

json.dump(dict(profile=args.profile, seed=args.seed, trials=args.trials, confirm=args.confirm, prios=PRIOS,
               deadline_ms=args.deadline, runs=log, minimal=cores), open(args.json, "w"), indent=1)

md = ["# Failure search", "",
      f"{args.trials} random combinations of one to {args.max_attackers} attackers at priority {args.prios} (the pipeline runs at 10), "
      f"profile `{args.profile}`, seed {args.seed}, {args.dur} s runs, {args.deadline} ms deadline. "
      f"A combination counts as failing only if the pipeline failed in all {args.confirm} runs. "
      f"{len(log)} distinct configurations were run in {(time.time() - t0) / 60:.0f} minutes. QEMU emulation.", ""]
if not cores:
    md += ["**No combination failed reliably.** In this search space nothing below or at the pipeline's priority broke it. "
           "That does not show it cannot be broken, only that these combinations did not.", ""]
else:
    md += ["| Minimal failing case | Priority | Kind |", "|---|---|---|"]
    for r in cores:
        md.append(f"| {' + '.join(f'`{a}`' for a in r['attackers'])} | {r['prio']} | {r['kind']} |")
    md += [""]
    for r in cores:
        if r["singles"]:
            md.append(f"* {' + '.join(r['attackers'])}: alone, " + ", ".join(f"`{a}` {'fails' if v else 'passes'}" for a, v in r["singles"].items()) + ".")
md += ["", "Limits: random search, so a case not listed was not found, not shown impossible. Emulator timing. "
       f"Raw runs: `{os.path.relpath(args.json, os.path.dirname(args.out))}`.", ""]
open(args.out, "w").write("\n".join(md))
print("\n".join(md))
