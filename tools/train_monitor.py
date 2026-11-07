#!/usr/bin/env python3
"""Train Siege's interference predictor from scratch (numpy only) and write pipeline/monitor.h.

    python3 tools/train_monitor.py docs/results/full-*.json [--out pipeline/monitor.h] [--report docs/predictor.md]

What it is. A small neural network (two hidden layers of 32 ReLU units, two heads) that
reads the first K seconds of a run's latency samples, as the controller reports them, and
predicts two things before the run ends:

    fail     will this run end in RESULT FAIL?                       (sigmoid head)
    pattern  if it fails, which family: CPU starvation, shared-service
             queue, lock inversion, or dead service                  (softmax head)

Everything is written here: the features, backpropagation, the Adam optimiser, weight
initialisation and the cross-validation. There is no deep-learning framework. The trained
weights are written as C arrays and evaluated by hand-written C in the controller
(pipeline/monitor.h), so the same network runs on the QNX target.

It sees only what a monitor on the target can see: per-second late and lost counts and
latency percentiles. It is never told which attacker is running or which profile is on.

Evaluation, in the report: (1) failure prediction is tested leave-one-attacker-out, so each
score is on an attack type the network never saw in training; (2) pattern classification is
tested with stratified 5-fold cross-validation, because lock inversion and dead service each
come from a single scenario and cannot be held out; (3) both are compared with a plain rule
that needs no learning.
"""
import argparse, collections, glob, json, math, os, sys
import numpy as np

here = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser()
ap.add_argument("files", nargs="+")
ap.add_argument("--out", default=os.path.join(here, "..", "pipeline", "monitor.h"))
ap.add_argument("--report", default=os.path.join(here, "..", "docs", "predictor.md"))
ap.add_argument("--json", default=os.path.join(here, "..", "docs", "results", "predictor.json"))
ap.add_argument("--hidden", type=int, default=32)
ap.add_argument("--epochs", type=int, default=400)
ap.add_argument("--seed", type=int, default=20261107)
ap.add_argument("--deadline-ms", type=float, default=20)
args = ap.parse_args()

KS = (1, 2, 3)               # seconds of evidence the network may use
FPS = 50.0
PATTERNS = ["CPU starvation", "shared-service queue", "lock inversion", "dead service"]
PER = 6
SCALE = math.log1p(5_000_000)


def pattern_of(row, fail):
    if not fail:
        return -1
    extra = row.get("extra") or {}
    if extra.get("KILL_AT") and not extra.get("SUPERVISE"):
        return 3
    atk = row.get("atk") or ""
    if atk == "pinv":
        return 2
    if atk in ("flood", "workflood", "pipeflood"):
        return 1
    return 0


def feat(samples, K):
    """K seconds of evidence -> PER*K numbers. A second the controller never reported is a silent
    second (present = 0 and everything else 0), which is itself a strong signal."""
    by_t = {int(s["t"]): s for s in samples}
    v = []
    for t in range(1, K + 1):
        s = by_t.get(t)
        if s is None:
            v += [0, 0, 0, 0, 0, 0]
        else:
            v += [1, min(s["late"] / FPS, 1.0), min(s["lost"] / FPS, 1.0),
                  math.log1p(s["p50"]) / SCALE, math.log1p(s["p99"]) / SCALE, math.log1p(s["max"]) / SCALE]
    return v


cells = {}                                   # (profile, scenario) -> rows; a later file replaces an earlier one with no more valid runs
for f in args.files:
    for sc in json.load(open(f)):
        if not isinstance(sc, dict) or not isinstance(sc.get("runs"), list):
            continue
        valid = [r for r in sc["runs"] if r]
        key = (sc.get("profile"), sc.get("scenario"))
        if key in cells and len(cells[key][1]) > len(valid):
            continue
        cells[key] = (sc, valid)
rows = []
for sc, valid in cells.values():
    for r in valid:
        rows.append(dict(atk=sc.get("atk") or "none", extra=sc.get("extra") or {}, profile=sc.get("profile"),
                         scenario=sc.get("scenario"), fail=bool(r["fail"]), samples=r.get("samples") or [],
                         abandoned=bool(r.get("abandoned"))))
if len(rows) < 200:
    sys.exit(f"only {len(rows)} runs: run ./siege test --runs 15 --json docs/results/full-<profile>.json for each profile first")
group = [("kill" if (r["extra"].get("KILL_AT")) else r["atk"]) for r in rows]
y_fail = np.array([r["fail"] for r in rows], dtype=np.float32)
y_pat = np.array([pattern_of(r, r["fail"]) for r in rows])
print(f"{len(rows)} runs, {int(y_fail.sum())} failing; groups: {dict(collections.Counter(group))}")

rng = np.random.default_rng(args.seed)


# ---- the network, by hand ---------------------------------------------------------------------
class Net:
    def __init__(self, nin, h, nout, rng):
        s = lambda a, b: rng.normal(0, math.sqrt(2.0 / a), (a, b)).astype(np.float32)
        self.p = dict(W1=s(nin, h), b1=np.zeros(h, np.float32), W2=s(h, h), b2=np.zeros(h, np.float32),
                      W3=s(h, nout) * 0.5, b3=np.zeros(nout, np.float32))
        self.m = {k: np.zeros_like(v) for k, v in self.p.items()}
        self.v = {k: np.zeros_like(v) for k, v in self.p.items()}
        self.t = 0

    def forward(self, X):
        p = self.p
        z1 = X @ p["W1"] + p["b1"]; a1 = np.maximum(z1, 0)
        z2 = a1 @ p["W2"] + p["b2"]; a2 = np.maximum(z2, 0)
        return X, z1, a1, z2, a2, a2 @ p["W3"] + p["b3"]

    def step(self, X, grad_out, lr=0.01, l2=1e-4):
        """grad_out: d loss / d output, shape (n, nout). One Adam update, backprop by hand."""
        p = self.p
        X, z1, a1, z2, a2, _ = self.forward(X)
        g = {}
        g["W3"] = a2.T @ grad_out; g["b3"] = grad_out.sum(0)
        d2 = (grad_out @ p["W3"].T) * (z2 > 0)
        g["W2"] = a1.T @ d2; g["b2"] = d2.sum(0)
        d1 = (d2 @ p["W2"].T) * (z1 > 0)
        g["W1"] = X.T @ d1; g["b1"] = d1.sum(0)
        self.t += 1
        for k in p:
            gk = g[k] / len(X) + (l2 * p[k] if k.startswith("W") else 0)
            self.m[k] = 0.9 * self.m[k] + 0.1 * gk
            self.v[k] = 0.999 * self.v[k] + 0.001 * gk * gk
            mh = self.m[k] / (1 - 0.9 ** self.t); vh = self.v[k] / (1 - 0.999 ** self.t)
            p[k] -= lr * mh / (np.sqrt(vh) + 1e-8)


def sigmoid(z): return 1 / (1 + np.exp(-np.clip(z, -30, 30)))


def softmax(z):
    e = np.exp(z - z.max(1, keepdims=True)); return e / e.sum(1, keepdims=True)


def train(X, yf, yp, seed, epochs):
    """One net, outputs [fail logit, 4 pattern logits]. Pattern loss only on failing runs."""
    r = np.random.default_rng(seed)
    net = Net(X.shape[1], args.hidden, 1 + len(PATTERNS), r)
    pos = max(yf.sum(), 1); neg = max(len(yf) - yf.sum(), 1)
    wf = np.where(yf == 1, len(yf) / (2 * pos), len(yf) / (2 * neg)).astype(np.float32)
    onehot = np.zeros((len(yf), len(PATTERNS)), np.float32)
    for i, c in enumerate(yp):
        if c >= 0: onehot[i, c] = 1
    for ep in range(epochs):
        idx = r.permutation(len(X))
        for b in range(0, len(X), 64):
            j = idx[b:b + 64]
            _, _, _, _, _, out = net.forward(X[j])
            go = np.zeros_like(out)
            go[:, 0] = (sigmoid(out[:, 0]) - yf[j]) * wf[j]
            has = (yf[j] == 1) & (yp[j] >= 0)
            go[:, 1:] = (softmax(out[:, 1:]) - onehot[j]) * has[:, None]
            net.step(X[j], go, lr=0.01 if ep < epochs * 0.7 else 0.003)
    return net


def predict(net, X):
    out = net.forward(X)[-1]
    return sigmoid(out[:, 0]), softmax(out[:, 1:])


def scores(pred, truth):
    tp = int(((pred == 1) & (truth == 1)).sum()); fp = int(((pred == 1) & (truth == 0)).sum())
    fn = int(((pred == 0) & (truth == 1)).sum()); tn = int(((pred == 0) & (truth == 0)).sum())
    pr = tp / (tp + fp) if tp + fp else 0.0; rc = tp / (tp + fn) if tp + fn else 0.0
    return dict(tp=tp, fp=fp, fn=fn, tn=tn, precision=pr, recall=rc, f1=(2 * pr * rc / (pr + rc)) if pr + rc else 0.0,
                accuracy=(tp + tn) / max(len(truth), 1))


def rule(samples, K):
    """The no-learning baseline: alarm if any of the first K seconds was silent, had a late or lost frame
    beyond 2%, or had a p99 above the deadline."""
    by_t = {int(s["t"]): s for s in samples}
    for t in range(1, K + 1):
        s = by_t.get(t)
        if s is None or s["late"] + s["lost"] > 0.02 * FPS or s["p99"] > args.deadline_ms * 1000:
            return 1
    return 0


# ---- evaluation ------------------------------------------------------------------------------------
res = {"runs": len(rows), "failing": int(y_fail.sum()), "by_K": {}, "seed": args.seed}
groups = sorted(set(group))
for K in KS:
    X = np.array([feat(r["samples"], K) for r in rows], np.float32)
    mu, sd = X.mean(0), X.std(0) + 1e-6
    pred_logo = np.zeros(len(rows))
    for g in groups:
        te = np.array([x == g for x in group]); tr = ~te
        if y_fail[tr].sum() == 0 or y_fail[tr].sum() == tr.sum():
            continue
        m, s_ = X[tr].mean(0), X[tr].std(0) + 1e-6
        net = train((X[tr] - m) / s_, y_fail[tr], y_pat[tr], args.seed, args.epochs // 2)
        pred_logo[te] = (predict(net, (X[te] - m) / s_)[0] > 0.5)
    base = np.array([rule(r["samples"], K) for r in rows])
    # pattern: stratified 5-fold over failing runs
    fi = np.where(y_pat >= 0)[0]
    folds = [[] for _ in range(5)]
    for c in range(len(PATTERNS)):
        ids = [i for i in fi if y_pat[i] == c]; rng.shuffle(ids)
        for k, i in enumerate(ids): folds[k % 5].append(i)
    correct = 0; conf = np.zeros((len(PATTERNS), len(PATTERNS)), int)
    for k in range(5):
        te = np.array(sorted(folds[k])); trn = np.array(sorted(set(range(len(rows))) - set(te.tolist())))
        m, s_ = X[trn].mean(0), X[trn].std(0) + 1e-6
        net = train((X[trn] - m) / s_, y_fail[trn], y_pat[trn], args.seed + k, args.epochs // 2)
        pp = predict(net, (X[te] - m) / s_)[1].argmax(1)
        for a, b in zip(y_pat[te], pp): conf[a, b] += 1
        correct += int((pp == y_pat[te]).sum())
    res["by_K"][K] = dict(network=scores(pred_logo, y_fail), rule=scores(base, y_fail),
                          pattern_accuracy=correct / max(len(fi), 1), pattern_confusion=conf.tolist())
    print(f"K={K}  network F1 {res['by_K'][K]['network']['f1']:.3f}  rule F1 {res['by_K'][K]['rule']['f1']:.3f}  "
          f"pattern accuracy {res['by_K'][K]['pattern_accuracy']:.3f}", flush=True)

# ---- final models, one per K, trained on everything, written as C -------------------------------------
models = {}
for K in KS:
    X = np.array([feat(r["samples"], K) for r in rows], np.float32)
    mu, sd = X.mean(0), X.std(0) + 1e-6
    net = train((X - mu) / sd, y_fail, y_pat, args.seed, args.epochs)
    models[K] = (mu, sd, net)
    pf, pp = predict(net, (X - mu) / sd)
    res["by_K"][K]["train_accuracy"] = float(((pf > 0.5) == (y_fail == 1)).mean())


def carr(name, a):
    flat = np.asarray(a, np.float32).ravel()
    return f"static const float {name}[{len(flat)}] = {{" + ", ".join(f"{x:.7g}f" for x in flat) + "};\n"


h = args.hidden
c = ["/* Generated by tools/train_monitor.py. Do not edit.\n",
     f" * Interference predictor: {len(KS)} networks (1, 2 and 3 seconds of evidence), 2 hidden layers of {h} ReLU units.\n",
     f" * Outputs: 1 failure logit and {len(PATTERNS)} pattern logits. Trained on {len(rows)} runs, seed {args.seed}. */\n",
     "#ifndef SIEGE_MONITOR_H\n#define SIEGE_MONITOR_H\n#include <math.h>\n\n",
     f"#define MON_PER_SECOND {PER}\n#define MON_HIDDEN {h}\n#define MON_PATTERNS {len(PATTERNS)}\n#define MON_MAX_K {max(KS)}\n",
     "static const char *const mon_pattern_name[MON_PATTERNS] = {" + ", ".join(f'"{p}"' for p in PATTERNS) + "};\n\n"]
for K, (mu, sd, net) in models.items():
    p = net.p
    c += [carr(f"mon{K}_mu", mu), carr(f"mon{K}_sd", sd), carr(f"mon{K}_W1", p["W1"]), carr(f"mon{K}_b1", p["b1"]),
          carr(f"mon{K}_W2", p["W2"]), carr(f"mon{K}_b2", p["b2"]), carr(f"mon{K}_W3", p["W3"]), carr(f"mon{K}_b3", p["b3"])]
c.append(r'''
typedef struct { const float *mu, *sd, *W1, *b1, *W2, *b2, *W3, *b3; } mon_net_t;
static const mon_net_t mon_nets[MON_MAX_K] = {
''')
for K in KS:
    c.append(f"    {{ mon{K}_mu, mon{K}_sd, mon{K}_W1, mon{K}_b1, mon{K}_W2, mon{K}_b2, mon{K}_W3, mon{K}_b3 }},\n")
c.append(r'''};

/* feat: K * MON_PER_SECOND numbers, laid out as feat() in tools/train_monitor.py.
 * Returns the probability that the run will fail; pat[] gets the pattern probabilities. */
static inline float monitor_predict(int k, const float *feat, float *pat)
{
    const mon_net_t *n = &mon_nets[k - 1];
    int nin = k * MON_PER_SECOND;
    float x[MON_MAX_K * MON_PER_SECOND], a1[MON_HIDDEN], a2[MON_HIDDEN], out[1 + MON_PATTERNS];
    for (int i = 0; i < nin; i++) x[i] = (feat[i] - n->mu[i]) / n->sd[i];
    for (int j = 0; j < MON_HIDDEN; j++) {
        float s = n->b1[j];
        for (int i = 0; i < nin; i++) s += x[i] * n->W1[i * MON_HIDDEN + j];
        a1[j] = s > 0 ? s : 0;
    }
    for (int j = 0; j < MON_HIDDEN; j++) {
        float s = n->b2[j];
        for (int i = 0; i < MON_HIDDEN; i++) s += a1[i] * n->W2[i * MON_HIDDEN + j];
        a2[j] = s > 0 ? s : 0;
    }
    for (int j = 0; j < 1 + MON_PATTERNS; j++) {
        float s = n->b3[j];
        for (int i = 0; i < MON_HIDDEN; i++) s += a2[i] * n->W3[i * (1 + MON_PATTERNS) + j];
        out[j] = s;
    }
    float mx = out[1], sum = 0;
    for (int j = 1; j <= MON_PATTERNS; j++) if (out[j] > mx) mx = out[j];
    for (int j = 1; j <= MON_PATTERNS; j++) { pat[j - 1] = expf(out[j] - mx); sum += pat[j - 1]; }
    for (int j = 0; j < MON_PATTERNS; j++) pat[j] /= sum;
    return 1.0f / (1.0f + expf(-out[0]));
}

#endif
''')
open(args.out, "w").write("".join(c))
print(f"wrote {args.out}")

# a test vector so the C side can be checked against numpy
K = 3
mu, sd, net = models[K]
X = np.array([feat(r["samples"], K) for r in rows[:5]], np.float32)
pf, pp = predict(net, (X - mu) / sd)
res["test_vectors"] = [dict(k=K, feat=[float(x) for x in X[i]], p_fail=float(pf[i]), pat=[float(x) for x in pp[i]]) for i in range(5)]
json.dump(res, open(args.json, "w"), indent=1)

# ---- report -------------------------------------------------------------------------------------------------
L = ["# Interference predictor", "",
     "A neural network written from scratch (numpy for training, plain C for inference on the target; no framework) that reads the "
     "first seconds of a run's latency samples and predicts whether the run will fail and which pattern it is. "
     f"Two hidden layers of {h} units, {sum(v.size for v in models[3][2].p.values())} weights per network. "
     f"Trained on {len(rows)} runs ({int(y_fail.sum())} failing) from the full matrix, QEMU emulation. "
     "It sees only per-second late and lost counts and latency percentiles; it is not told the attacker or the profile.", "",
     "## Does it warn early, and better than a plain rule?", "",
     "Failure prediction, tested leave-one-attacker-out: each score is on an attack type the network was not trained on. "
     "The rule alarms on any silent second, more than 2% late or lost frames, or a p99 over the deadline.", "",
     "| Seconds of evidence | Network F1 | Network recall | Network precision | Rule F1 | Rule recall | Rule precision |", "|---|---|---|---|---|---|---|"]
for K in KS:
    n, r_ = res["by_K"][K]["network"], res["by_K"][K]["rule"]
    L.append(f"| {K} | {n['f1']:.2f} | {n['recall']:.2f} | {n['precision']:.2f} | {r_['f1']:.2f} | {r_['recall']:.2f} | {r_['precision']:.2f} |")
L += ["", "## Verdict", ""]
wins = [K for K in KS if res["by_K"][K]["network"]["f1"] > res["by_K"][K]["rule"]["f1"] + 0.02]
ties = [K for K in KS if abs(res["by_K"][K]["network"]["f1"] - res["by_K"][K]["rule"]["f1"]) <= 0.02]
loses = [K for K in KS if res["by_K"][K]["network"]["f1"] < res["by_K"][K]["rule"]["f1"] - 0.02]
if wins: L.append(f"* The network beats the rule on unseen attackers with {', '.join(map(str, wins))} s of evidence (F1 margin over 0.02).")
if ties: L.append(f"* It ties the rule (within 0.02 F1) with {', '.join(map(str, ties))} s.")
if loses: L.append(f"* The rule is better with {', '.join(map(str, loses))} s.")
earliest = min(wins) if wins else None
rule_early = min([K for K in KS if res["by_K"][K]["rule"]["f1"] >= 0.85] or [None], key=lambda x: x or 99)
L.append(f"* The plain rule already reaches F1 0.85 with {rule_early} s of evidence, so the network does not warn earlier than a rule that costs nothing to write; "
         "what it adds, where it wins, is fewer false alarms." if wins and rule_early and earliest and earliest >= rule_early else
         "* See the table: the network's value is where it wins, and the rule is the thing to beat.")
L += ["", "Pattern classification among failing runs, 5-fold cross-validation (lock inversion and dead service each come from "
      "one scenario, so they cannot be held out; this measures how separable the patterns are, not generalisation to new attacks):", "",
      "| Seconds of evidence | Accuracy |", "|---|---|"]
for K in KS:
    L.append(f"| {K} | {res['by_K'][K]['pattern_accuracy']:.2f} |")
L += ["", "Confusion matrix at 3 seconds (rows: true pattern, columns: predicted):", "",
      "| | " + " | ".join(PATTERNS) + " |", "|---|" + "---|" * len(PATTERNS)]
for i, row in enumerate(res["by_K"][3]["pattern_confusion"]):
    L.append(f"| {PATTERNS[i]} | " + " | ".join(str(x) for x in row) + " |")
L += ["", "## Limits", "",
      "* Trained and tested on emulator data from one image and one deadline (20 ms). On hardware the timings, and so the features, would differ and it would need retraining.",
      "* Leave-one-attacker-out is a hard test, but the attacks come from one author and share structure (several are CPU hogs in different clothes).",
      "* The network cannot know why a run is failing, only that its latency looks like runs that failed. It is an early-warning signal, not a diagnosis.",
      "* The numbers here come from the results files in `docs/results/full-*.json` and are regenerated by `tools/train_monitor.py`.", ""]
open(args.report, "w").write("\n".join(L))
print("\n".join(L))
