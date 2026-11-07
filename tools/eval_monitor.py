#!/usr/bin/env python3
"""Score the on-target predictor against what actually happened, on fresh runs.

    python3 tools/eval_monitor.py examples/monitor/results/*.json [--out docs/predictor-online.md]

The runs come from `./siege test --config examples/monitor/siege.json`, which runs the controller
with MONITOR=1. The network ran inside the controller on QNX, in a thread above every other priority,
and printed one prediction per second of evidence (1, 2 and 3 s). The alarm is the first prediction
at or above 0.5. These runs were not used for training. The name-squatting scenarios involve an
attacker the network has never seen.

Baseline: a plain rule on the same runs, alarming if any of the first K seconds was silent, had more
than 2% late or lost frames, or had a p99 over the deadline.
"""
import argparse, collections, json, os, sys

ap = argparse.ArgumentParser()
ap.add_argument("files", nargs="+")
ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "predictor-online.md"))
ap.add_argument("--deadline-ms", type=float, default=20)
ap.add_argument("--run-ms", type=int, default=5000)
args = ap.parse_args()
PATTERNS = ["CPU starvation", "shared-service queue", "lock inversion", "dead service"]


def true_pattern(sc, fail):
    if not fail: return None
    extra = sc.get("extra") or {}
    if extra.get("KILL_AT") and not extra.get("SUPERVISE"): return "dead service"
    atk = sc.get("atk") or ""
    if atk == "pinv": return "lock inversion"
    if atk in ("flood", "workflood", "pipeflood"): return "shared-service queue"
    return "CPU starvation"


def rule(samples, K):
    by_t = {int(s["t"]): s for s in samples}
    for t in range(1, K + 1):
        s = by_t.get(t)
        if s is None or s["late"] + s["lost"] > 1 or s["p99"] > args.deadline_ms * 1000:
            return True
    return False


rows = []
for f in args.files:
    for sc in json.load(open(f)):
        for r in sc["runs"]:
            if not r or not r.get("monitor"):
                continue
            ev = {m["k"]: m for m in r["monitor"]}
            rows.append(dict(scenario=sc["scenario"], profile=sc["profile"], atk=sc.get("atk") or "none",
                             fail=bool(r["fail"]), ev=ev, samples=r.get("samples") or [],
                             truth=true_pattern(sc, bool(r["fail"]))))


def alarm(r, K):
    for k in range(1, K + 1):
        m = r["ev"].get(k)
        if m and m["p_fail"] >= 0.5:
            return m
    return None


def score(pairs):
    tp = sum(1 for p, t in pairs if p and t); fp = sum(1 for p, t in pairs if p and not t)
    fn = sum(1 for p, t in pairs if not p and t); tn = sum(1 for p, t in pairs if not p and not t)
    pr = tp / (tp + fp) if tp + fp else 0.0; rc = tp / (tp + fn) if tp + fn else 0.0
    return dict(n=len(pairs), tp=tp, fp=fp, fn=fn, tn=tn, precision=pr, recall=rc,
                f1=2 * pr * rc / (pr + rc) if pr + rc else 0.0)


L = ["# Predictor, scored online", "",
     f"{len(rows)} fresh runs on QNX in QEMU with the predictor running inside the controller (thread priority above all other "
     "work), not used for training. An alarm is the first prediction at or above 0.5 using up to K seconds of evidence.", "",
     "| Seconds of evidence | Network F1 | Recall | Precision | Rule F1 | Recall | Precision |", "|---|---|---|---|---|---|---|"]
res = {}
for K in (1, 2, 3):
    n = score([(alarm(r, K) is not None, r["fail"]) for r in rows])
    b = score([(rule(r["samples"], K), r["fail"]) for r in rows])
    res[K] = dict(network=n, rule=b)
    L.append(f"| {K} | {n['f1']:.2f} | {n['recall']:.2f} | {n['precision']:.2f} | {b['f1']:.2f} | {b['recall']:.2f} | {b['precision']:.2f} |")

L += ["", "## When it warns", ""]
lead = [args.run_ms - alarm(r, 3)["at_ms"] for r in rows if r["fail"] and alarm(r, 3)]
if lead:
    lead.sort()
    L.append(f"For failing runs that it flagged, the alarm came a median of {lead[len(lead)//2]/1000:.1f} s before the end of a "
             f"{args.run_ms/1000:.0f} s run (earliest {max(lead)/1000:.1f} s, latest {min(lead)/1000:.1f} s). "
             "The verdict itself comes only at the end of the run.")

L += ["", "## Pattern named at the alarm (failing runs that were flagged)", "", "| True pattern | Runs | Named correctly | Most common wrong answer |", "|---|---|---|---|"]
for pat in PATTERNS:
    sub = [r for r in rows if r["truth"] == pat and alarm(r, 3)]
    if not sub: continue
    right = sum(1 for r in sub if alarm(r, 3)["pattern"].strip() == pat)
    wrong = collections.Counter(alarm(r, 3)["pattern"].strip() for r in sub if alarm(r, 3)["pattern"].strip() != pat)
    L.append(f"| {pat} | {len(sub)} | {right} | {wrong.most_common(1)[0][0] if wrong else '-'} |")

squat = [r for r in rows if r["atk"] == "squat"]
if squat:
    n = score([(alarm(r, 3) is not None, r["fail"]) for r in squat]); b = score([(rule(r["samples"], 3), r["fail"]) for r in squat])
    L += ["", "## An attacker the network has never seen: name squatting", "",
          f"{len(squat)} runs ({sum(r['fail'] for r in squat)} failed). Network: {n['tp']} caught, {n['fn']} missed, {n['fp']} false alarms. "
          f"Rule: {b['tp']} caught, {b['fn']} missed, {b['fp']} false alarms."]

fa = [r for r in rows if not r["fail"] and alarm(r, 3)]
L += ["", "## False alarms", "", f"{len(fa)} of {sum(1 for r in rows if not r['fail'])} passing runs raised an alarm."]
if fa:
    c = collections.Counter(r["scenario"] for r in fa)
    L.append("Most: " + ", ".join(f"{s} ({k})" for s, k in c.most_common(4)) + ".")
L += ["", "## Limits", "",
      "* Fresh runs, but of the same scenarios the network was trained on, apart from name squatting. This tests repeatability, not breadth.",
      "* QEMU emulation, one image, one 20 ms deadline.",
      "* The network only reads latency; a pass or fail it predicts is the controller's verdict, not a diagnosis of cause.", ""]
open(args.out, "w").write("\n".join(L))
json.dump(res, open(args.out.replace(".md", ".json").replace("docs", "docs/results") if False else os.path.join(os.path.dirname(args.out), "results", "predictor-online.json"), "w"), indent=1)
print("\n".join(L))
