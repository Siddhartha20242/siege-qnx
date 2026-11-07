#!/usr/bin/env python3
"""Map where an attack starts to break the pipeline, and learn that boundary with few runs.

    ./siege frontier measure            run the whole priority x request-rate grid once (slow, ground truth)
    ./siege frontier replay             compare ways of choosing which cells to run, on that measured grid
    ./siege frontier active --budget 14 run only the cells a learner picks, then print the boundary

Every attacker in siege.json is a point someone chose. Here the attack has two
dials: the priority it runs at and how many requests per second each of its threads
sends (workflood: each request costs the shared detector real work). The question
is the weakest attack that still breaks the pipeline. Running every cell finds it
but is slow, so a small model (logistic regression on priority and log rate, written
here in numpy, no libraries) is trained on the cells run so far, and the next cell
is the one it is least sure about. `replay` measures whether that beats picking
cells at random, using the full grid as the answer key.
"""
import argparse, json, math, os, random, sys, time
import numpy as np

here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, here)

PRIOS = [5, 10, 15, 20, 30, 50]                 # the pipeline runs at 10
RATES = [5, 10, 20, 35, 60, 100, 170, 300, 0]    # requests/s per thread; 0 = as fast as the attacker can
CELLS = [(p, r) for p in PRIOS for r in RATES]
GRID_JSON = os.path.join(here, "..", "docs", "results", "frontier-grid.json")


def feat(cell):
    """Features: priority (scaled), log rate (scaled; unlimited counts as 1000/s), and their squares and product."""
    p, r = cell
    x = (math.log(p) - math.log(5)) / (math.log(50) - math.log(5))
    y = (math.log(r if r else 1000) - math.log(5)) / (math.log(1000) - math.log(5))
    return np.array([1.0, x, y, x * x, y * y, x * y])


class Logistic:
    """Plain logistic regression, batch gradient descent, small L2 penalty."""

    def __init__(self):
        self.w = np.zeros(6)

    def fit(self, cells, labels, steps=400, lr=1.0, l2=0.01):
        X = np.stack([feat(c) for c in cells])
        y = np.array(labels, dtype=float)
        w = np.zeros(X.shape[1])
        for _ in range(steps):
            p = 1 / (1 + np.exp(-np.clip(X @ w, -30, 30)))
            w -= lr * (X.T @ (p - y) / len(y) + l2 * w)
        self.w = w
        return self

    def prob(self, cell):
        return float(1 / (1 + math.exp(-max(-30, min(30, feat(cell) @ self.w)))))


def seed_cells(rng, k=4):
    return rng.sample(CELLS, k)


def next_cell(known, rng):
    """Uncertainty sampling: the unmeasured cell whose predicted failure chance is closest to 1/2."""
    rest = [c for c in CELLS if c not in known]
    if len(set(known.values())) < 2:                 # nothing learned yet: all one label, so spread out
        return rng.choice(rest)
    m = Logistic().fit(list(known), list(known.values()))
    return min(rest, key=lambda c: (abs(m.prob(c) - 0.5), rng.random()))


def predict_all(known):
    if len(set(known.values())) < 2:
        label = next(iter(known.values()))
        return {c: label for c in CELLS}
    m = Logistic().fit(list(known), list(known.values()))
    return {c: m.prob(c) >= 0.5 for c in CELLS}


def accuracy(known, truth):
    pred = predict_all(known)
    return sum(pred[c] == truth[c] for c in CELLS) / len(CELLS)


def strategy_pick(name, known, rng):
    if name == "active":
        return next_cell(known, rng)
    return rng.choice([c for c in CELLS if c not in known])        # random


def run_strategy(name, truth, budget, seed):
    rng = random.Random(seed)
    known = {c: truth[c] for c in seed_cells(rng)}
    while len(known) < budget:
        c = strategy_pick(name, known, rng)
        known[c] = truth[c]
    return accuracy(known, truth)


def load_truth(path=GRID_JSON):
    d = json.load(open(path))
    truth = {}
    for row in d["cells"]:
        truth[(row["prio"], row["rate"])] = row["fails"] * 2 > row["runs"]      # majority of runs failed
    missing = [c for c in CELLS if c not in truth]
    if missing:
        sys.exit(f"{path} lacks cells {missing}")
    return truth, d


def measure_cell(c, args, prio, rate):
    fails = 0
    for _ in range(args.runs):
        out = c.run(f'PROFILE={args.profile} DEADLINE_MS={args.deadline} ATK="workflood" ATK_PRIO={prio} '
                    f'ATK_RATE={rate or ""} pipeline.sh {args.dur}'.replace("ATK_RATE= ", ""), args.dur * 8 + 30)
        fails += "RESULT FAIL" in out
    return fails


def cmd_measure(args):
    from qnxconsole import Console
    cells, t0 = [], time.time()
    with Console(args.image) as c:
        c.run("pipeline.sh 3 >/dev/null", 60)
        for i, (p, r) in enumerate(CELLS):
            f = measure_cell(c, args, p, r)
            cells.append(dict(prio=p, rate=r, runs=args.runs, fails=f))
            print(f"prio {p:2d} rate {r or 'max':>4}: {f}/{args.runs} failed", flush=True)
            if (i + 1) % 18 == 0:                                   # fresh boot now and then; see docs/more-attackers.md
                c.close()
                c.__init__(args.image)
                c.run("pipeline.sh 3 >/dev/null", 60)
    json.dump(dict(profile=args.profile, deadline_ms=args.deadline, dur_s=args.dur, runs=args.runs, target="emulator",
                   attacker="workflood", work_passes=150, threads=2, minutes=round((time.time() - t0) / 60, 1),
                   cells=cells), open(GRID_JSON, "w"), indent=1)
    print("wrote", os.path.normpath(GRID_JSON))


def grid_table(truth):
    head = "| rate/thread \\ priority | " + " | ".join(str(p) for p in PRIOS) + " |"
    rows = [head, "|---|" + "---|" * len(PRIOS)]
    for r in RATES:
        rows.append(f"| {r or 'max'} req/s | " + " | ".join("**fail**" if truth[(p, r)] else "pass" for p in PRIOS) + " |")
    return "\n".join(rows)


def cmd_replay(args):
    truth, d = load_truth()
    seeds = range(args.seeds)
    lines = [f"Answer key: {len(CELLS)} cells measured, {d['runs']} runs each; a cell counts as failing if most runs failed "
             f"({sum(truth.values())} of {len(CELLS)} fail). Accuracy = share of all cells the model classifies correctly "
             f"after seeing only the budgeted cells; mean over {args.seeds} seeds with the 5th-95th percentile range.", "",
             "| Cells run | Random choice | Learner's choice |", "|---|---|---|"]
    out = {}
    for b in args.budgets:
        row = []
        for name in ("random", "active"):
            accs = np.array([run_strategy(name, truth, b, s) for s in seeds])
            out[f"{name}_{b}"] = [float(accs.mean()), float(np.percentile(accs, 5)), float(np.percentile(accs, 95))]
            row.append(f"{accs.mean():.0%} ({np.percentile(accs, 5):.0%}-{np.percentile(accs, 95):.0%})")
        lines.append(f"| {b} of {len(CELLS)} | {row[0]} | {row[1]} |")
    print("\n".join(lines))
    json.dump(dict(seeds=args.seeds, budgets=args.budgets, results=out, table=lines),
              open(args.out, "w"), indent=1)


def cmd_active(args):
    from qnxconsole import Console
    rng = random.Random(args.seed)
    known = {}
    with Console(args.image) as c:
        c.run("pipeline.sh 3 >/dev/null", 60)
        while len(known) < args.budget:
            cell = seed_cells(rng, 1)[0] if len(known) < 4 else next_cell(known, rng)
            if cell in known:
                continue
            f = measure_cell(c, args, *cell)
            known[cell] = f * 2 > args.runs
            print(f"prio {cell[0]:2d} rate {cell[1] or 'max':>4}: {f}/{args.runs} failed", flush=True)
    pred = predict_all(known)
    print("\nPredicted boundary (the model's guess for every cell; * = actually run):")
    for r in RATES:
        print(f"  {r or 'max':>4} req/s  " + "  ".join(("F" if pred[(p, r)] else ".") + ("*" if (p, r) in known else " ") for p in PRIOS))
    print("           " + "  ".join(f"{p:2d}" for p in PRIOS) + "   (priority)")


ap = argparse.ArgumentParser()
ap.add_argument("mode", choices=["measure", "replay", "active"])
ap.add_argument("--profile", default="none")
ap.add_argument("--runs", type=int, default=3, help="runs per cell")
ap.add_argument("--dur", type=int, default=5)
ap.add_argument("--deadline", type=int, default=20)
ap.add_argument("--budget", type=int, default=14)
ap.add_argument("--seed", type=int, default=1)
ap.add_argument("--seeds", type=int, default=300, help="replay: how many random seeds")
ap.add_argument("--budgets", type=lambda s: [int(x) for x in s.split(",")], default=[6, 8, 10, 14, 18, 24])
ap.add_argument("--out", default=os.path.join(here, "..", "docs", "results", "frontier-replay.json"), help="replay: where to write the numbers")
ap.add_argument("--image", default=os.path.join(here, "..", "build", "siege.ifs"))
args = ap.parse_args()
{"measure": cmd_measure, "replay": cmd_replay, "active": cmd_active}[args.mode](args)
