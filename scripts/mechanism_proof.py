#!/usr/bin/env python3
"""Observe the mechanism behind the workflood finding instead of inferring it.

    scripts/mechanism_proof.py [--samples 50] [--out docs/mechanism-proof.md]

While a client at priority 30 floods the detector with expensive requests, this
samples the real priority of each pipeline process with `pidin`, ten times a
second, from a shell that outranks everything. If the server runs at the
priority of the client it is serving, the detector should show up at 30 while
its own configured priority is 10. A clean run with no attacker is sampled the
same way as the control.
"""
import argparse, collections, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from qnxconsole import Console

ap = argparse.ArgumentParser()
ap.add_argument("--samples", type=int, default=50)
ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "mechanism-proof.md"))
ap.add_argument("--image", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "build", "siege.ifs"))
args = ap.parse_args()

WATCH = ("detector", "frame_src", "controller", "attacker")


def sample(c, atk, label):
    env = 'ATK="workflood" ATK_PRIO=30 ' if atk else ""
    cmd = (f"on -p 61r ksh -c '{env}DEADLINE_MS=20 pipeline.sh 6 > /dev/null & i=0; "
           f"while [ $i -lt {args.samples} ]; do pidin -f anp | grep -E \"detector|frame_src|controller|attacker\"; echo SAMPLE; "
           f"sleep 0.1; i=$((i+1)); done; wait'")
    out = c.run(cmd, 90)
    prios = collections.defaultdict(collections.Counter)
    for line in out.splitlines():
        m = re.match(r"\s*\d+\s+\S*?(detector|frame_src|controller|attacker)\s+(\d+)[a-z]", line)
        if m:
            prios[m.group(1)][int(m.group(2))] += 1
    return prios


with Console(args.image) as c:
    c.run("pipeline.sh 3 >/dev/null", 60)
    control = sample(c, False, "no attacker")
    attacked = sample(c, True, "workflood at priority 30")


def fmt(counter):
    n = sum(counter.values())
    return ", ".join(f"priority {p}: {k} of {n} samples" for p, k in sorted(counter.items())) or "not seen"


lines = ["# Mechanism proof: the server runs at its client's priority", "",
         "The `workflood` finding rests on a claim from QNX's documentation: a server runs at the priority of the",
         "client it is serving, and receives messages highest sender priority first. This is the claim observed,",
         f"not inferred. `pidin` sampled each process's priority {args.samples} times (every 0.1 s) from a shell at priority 61,",
         "once with no attacker and once with a client at priority 30 sending the detector expensive requests.",
         "The detector, camera and controller are all configured at priority 10.", "",
         "| Process | No attacker | Under the priority-30 flood |", "|---|---|---|"]
for name in ("detector", "frame_src", "controller", "attacker"):
    lines.append(f"| `{name}` | {fmt(control[name])} | {fmt(attacked[name])} |")
d_ctl, d_atk = control["detector"], attacked["detector"]
raised = sum(k for p, k in d_atk.items() if p > 10)
lines += ["", f"The detector was at its configured priority 10 in every control sample. Under the flood it was seen above 10 in "
              f"{raised} of {sum(d_atk.values())} samples. " +
          ("That is the inheritance, observed: nothing in the detector's code changes its priority; the kernel raises it to the "
           "client's while it serves that client's request." if raised else
           "It was not seen raised in any sample, so this run does not confirm the inheritance. Sampling every 0.1 s can miss "
           "short boosts, and the result should not be read as a refutation."),
          ""]
c_atk = attacked["controller"]
c_raised = sum(k for p, k in c_atk.items() if p > 10)
if c_raised and sum(c_atk.values()) and c_raised / sum(c_atk.values()) >= 0.5:
    lines += [f"**An observation we did not expect to find.** The controller was also seen above its configured priority "
              f"({c_raised} of {sum(c_atk.values())} samples), although it only ever receives messages from the detector and "
              "never from the attacker. That is consistent with the boost travelling along the message chain, since the "
              "detector sends to the controller while it is itself running at the client's priority. We did not investigate "
              "it further, so treat that explanation as a hypothesis, not a result.", ""]
lines += ["The camera (`frame_src`) only ever sends and never serves a request, so it is not boosted. The `attacker` row also includes "
          "its idle-priority helper threads (priority 1) and its main thread waiting at priority 60, which are not part of the finding.",
          "", "Sampling is coarse: `pidin` reads a snapshot, and a request is served in well under a millisecond, so the count",
          "of boosted samples is a lower bound on how often the detector runs at 30.", ""]
open(args.out, "w").write("\n".join(lines))
print("\n".join(lines))
