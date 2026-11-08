#!/usr/bin/env python3
"""Generate a safety-style test report from Siege results.

    scripts/testreport.py res-*.json deep-*.json --out docs/test-report

The structure is the one a safety engineer expects of an interference test
record: scope, test object, pass criteria, numbered test cases with expected and
observed results, a requirement-to-test traceability matrix, the environment, and
the limits of what the evidence shows, with a sign-off block. It reports
evidence from stress tests. It is not a safety case and not a certification claim.
"""
import argparse, datetime, html, json, os, subprocess, sys

here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, here)
from siegelib import aggregate, wilson, observed_verdict

ap = argparse.ArgumentParser()
ap.add_argument("files", nargs="+")
ap.add_argument("--config", default=os.path.join(here, "..", "siege.json"))
ap.add_argument("--out", default="test-report")
ap.add_argument("--max-fail-rate", type=float, default=0.2)
args = ap.parse_args()

cfg = json.load(open(args.config)) if os.path.exists(args.config) else {}
order = [s["label"] for s in cfg.get("scenarios", [])]
expect = {s["label"]: s.get("expect", {}) for s in cfg.get("scenarios", [])}

# (code, channel, derived requirement)
CHANNELS = [
    ("EXE", "Execution time", "The pipeline shall meet its frame deadline while another process competes for CPU time.",
     lambda m: m["atk"] in ("cpu", "ai")),
    ("MEM", "Memory", "The pipeline shall meet its frame deadline while another process holds and touches memory.",
     lambda m: m["atk"] == "mem"),
    ("MSG", "Message exchange", "The pipeline shall meet its frame deadline while another client abuses a service it shares.",
     lambda m: m["atk"] in ("flood", "workflood", "pipeflood")),
    ("KOB", "Kernel objects", "The pipeline shall meet its frame deadline while another process exhausts descriptors, channels and connections.",
     lambda m: m["atk"] == "fd"),
    ("PRC", "Process failure", "The pipeline shall meet its frame deadline while another process crashes and restarts repeatedly.",
     lambda m: m["atk"] == "crash"),
    ("LCK", "Shared locks", "The pipeline shall meet its frame deadline while a low-priority process holds a lock the pipeline needs.",
     lambda m: m["atk"] == "pinv"),
    ("SVC", "Service failure", "The pipeline shall resume delivering frames within the recovery budget after one of its stages is killed.",
     lambda m: not m["atk"] and "KILL_AT" in m["extra"]),
]

rows = []
for f in args.files:
    rows += json.load(open(f))
best = {}
for r in rows:
    k = (r["scenario"], r["profile"])
    if k not in best or sum(1 for x in r["runs"] if x) >= sum(1 for x in best[k]["runs"] if x):   # more valid runs wins; a tie goes to the later file
        best[k] = r
rows = list(best.values())
profiles = [p for p in ("none", "prio", "isolate", "budget", "secpol-connect", "secpol-ceiling", "secpol-names", "secpol", "secpol-least", "secpol-minimal") if any(r["profile"] == p for r in rows)]
scenarios = sorted({r["scenario"] for r in rows}, key=lambda s: order.index(s) if s in order else len(order))
meta = {r["scenario"]: dict(atk=r.get("atk", ""), extra=r.get("extra", {}) or {}) for r in rows}
targets = sorted({r.get("target", "emulator") for r in rows})
target_text = ("QEMU emulation (aarch64le, virt machine, 2 CPUs, software emulation)" if targets == ["emulator"]
               else "; ".join(targets))


def git_rev():
    try:
        repo = os.path.join(here, "..")
        rev = subprocess.run(["git", "-C", repo, "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True, timeout=5).stdout.strip() or "unknown"
        dirty = subprocess.run(["git", "-C", repo, "status", "--porcelain", "--untracked-files=no"],
                               capture_output=True, text=True, timeout=5).stdout.strip()
        return rev + (" + uncommitted changes" if dirty and rev != "unknown" else "")
    except OSError:
        return "unknown"


# ---- build the test cases -----------------------------------------------------------------
cases, by_channel = [], {c[0]: [] for c in CHANNELS}
seq = {c[0]: 0 for c in CHANNELS}
for sc in scenarios:
    code = next((c[0] for c in CHANNELS if c[3](meta[sc])), None)
    if code is None:
        code = "BAS"
        seq.setdefault("BAS", 0)
        by_channel.setdefault("BAS", [])
    seq[code] += 1
    for p in profiles:
        r = best.get((sc, p))
        if not r:
            continue
        agg = aggregate(r["runs"])
        n = len(r["runs"])
        fails = agg["fails"] if agg else n
        obs = observed_verdict(fails, n, args.max_fail_rate)
        want = expect.get(sc, {}).get(p, "pass")
        lo, hi = wilson(fails, n)
        case = dict(id=f"TC-{code}-{seq[code]:02d}/{p}", code=code, scenario=sc.strip(), profile=p, n=n, fails=fails,
                    ci=f"{lo}-{hi}%", expected=want, observed=obs, ok=obs == want,
                    worst=(agg["worst"] / 1000.0) if agg else None, gap=agg["gap"] if agg else None)
        cases.append(case)
        by_channel[code].append(case)

matched = sum(1 for c in cases if c["ok"])
rev = git_rev()
today = datetime.date.today().isoformat()
deadline = cfg.get("deadline_ms", "?")
tol = cfg.get("tolerance_permille", 20) / 10.0
recovery = cfg.get("recovery_ms", 500)

CRITERIA = [
    f"A run PASSES when at most {tol:.1f}% of its frames are late (more than {deadline} ms from the instant the frame was due) or lost.",
    f"A run FAILS if the pipeline is silent for longer than {recovery} ms, or never resumes (the controller gives up after 3 s).",
    "When the trained-network detector is used, a run also FAILS if more than 5% of checked detections are wrong (more than 1 pixel from the true position).",
    f"A test case is OBSERVED as pass when at most {args.max_fail_rate * 100:.0f}% of its runs fail, otherwise fail.",
    "A test case is a MATCH when its observed result equals its expected result. Expected failures are declared in siege.json (a known weakness of an unhardened configuration is an expected fail, and is reported as a match).",
]
LIMITS = [
    "All timing is from QEMU emulation. It is not hardware timing, and no result here has been reproduced on a real target.",
    "The pipeline and its input are synthetic. Every run sees the same frames, which makes runs comparable but does not represent a real sensor.",
    "The number of runs per case is small (5 to 15). A case with no observed failure is consistent with a failure rate up to the upper confidence bound (43% at 5 runs).",
    "Only the interference mechanisms listed above were tried. Passing every case does not show freedom from interference in general.",
    "Adaptive partitioning is not part of the free SDK and was not evaluated; sporadic scheduling budgets were used for CPU limits.",
]

# ---- markdown ---------------------------------------------------------------------------
md = [f"# Siege interference test report", "",
      "| | |", "|---|---|",
      f"| Document | Interference test record |", f"| Date | {today} |", f"| Tool revision | `{rev}` |",
      f"| Test object | Reference camera - detector - controller pipeline on QNX SDP 8.0 |",
      f"| Test environment | {target_text} |",
      f"| Configuration | deadline {deadline} ms, tolerance {tol:.1f}%, recovery budget {recovery} ms |",
      f"| Result | {matched} of {len(cases)} test cases matched their expected result |", "",
      f"> **Scope and status.** This document records evidence from stress tests of a stand-in pipeline on an emulator. "
      f"It is not a safety case, not a proof of freedom from interference, and not a certification claim.", "",
      "## 1. Pass criteria", ""] + [f"{i}. {t}" for i, t in enumerate(CRITERIA, 1)]
md += ["", "## 2. Requirements and traceability", "",
       "Derived requirements for this evaluation (not taken from a standard), each traced to the test cases that exercise it.", "",
       "| Requirement | Statement | Test cases | Matched |", "|---|---|---|---|"]
for code, name, stmt, _ in CHANNELS:
    cs = by_channel.get(code, [])
    if not cs:
        continue
    ids = sorted({c["id"].split("/")[0] for c in cs})
    md.append(f"| REQ-{code} | {stmt} | {', '.join(ids)} | {sum(1 for c in cs if c['ok'])}/{len(cs)} |")
md += ["", "## 3. Test cases", "",
       "| ID | Stimulus | Configuration | Runs | Failed (95% CI) | Expected | Observed | Result | Worst frame | Longest silence |",
       "|---|---|---|---|---|---|---|---|---|---|"]
for c in cases:
    wf = "-" if c["worst"] is None else (f"{c['worst']:.1f} ms" if c["worst"] < 1000 else f"{c['worst']/1000:.1f} s")
    md.append(f"| {c['id']} | {c['scenario']} | {c['profile']} | {c['n']} | {c['fails']}/{c['n']} ({c['ci']}) | "
              f"{c['expected']} | {c['observed']} | {'MATCH' if c['ok'] else '**MISMATCH**'} | {wf} | {c['gap']} ms |")
md += ["", "## 4. Environment", "",
       f"* Target: {target_text}.", "* Operating system: QNX SDP 8.0 (QNX Everywhere, non-commercial licence), toolchain `qcc -Vgcc_ntoaarch64le`.",
       f"* Tool revision: `{rev}`. Raw runs: `docs/results/`.",
       "* Configurations under test: `none` (default round-robin, priority 10), `prio` (pipeline at priority 40), "
       "`isolate` (pipeline on CPU 1, attackers on CPU 0), `budget` (attackers capped by SCHED_SPORADIC, 10 ms per 100 ms).",
       "", "## 5. Limits of this evidence", ""] + [f"* {t}" for t in LIMITS]
md += ["", "## 6. Review", "", "| Role | Name | Date | Signature |", "|---|---|---|---|",
       "| Author | | | |", "| Reviewer | | | |", ""]
open(args.out + ".md", "w").write("\n".join(md))

# ---- html (print friendly) ---------------------------------------------------------------
def tr(cells, tag="td", cls=""):
    return f"<tr{(' class=' + cls) if cls else ''}>" + "".join(f"<{tag}>{html.escape(str(c))}</{tag}>" for c in cells) + "</tr>"


rowshtml = ""
for c in cases:
    wf = "-" if c["worst"] is None else (f"{c['worst']:.1f} ms" if c["worst"] < 1000 else f"{c['worst']/1000:.1f} s")
    rowshtml += tr([c["id"], c["scenario"], c["profile"], c["n"], f"{c['fails']}/{c['n']} ({c['ci']})", c["expected"],
                    c["observed"], "MATCH" if c["ok"] else "MISMATCH", wf, f"{c['gap']} ms"], cls="ok" if c["ok"] else "bad")
reqhtml = ""
for code, name, stmt, _ in CHANNELS:
    cs = by_channel.get(code, [])
    if cs:
        ids = ", ".join(sorted({c["id"].split("/")[0] for c in cs}))
        reqhtml += tr([f"REQ-{code}", stmt, ids, f"{sum(1 for c in cs if c['ok'])}/{len(cs)}"])
page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Siege interference test report</title>
<style>body{{font:14px/1.5 system-ui,sans-serif;max-width:1000px;margin:24px auto;padding:0 16px;color:#1c2330}}
table{{border-collapse:collapse;width:100%;margin:8px 0 20px}}th,td{{border:1px solid #cfd6e0;padding:5px 8px;text-align:left;vertical-align:top}}
th{{background:#f0f3f7}}tr.bad td{{background:#fbdcdc}}h1{{margin-bottom:4px}}.note{{border-left:4px solid #bf8700;background:#fdf6df;padding:8px 12px}}
@media print{{body{{margin:0}}}}</style></head><body>
<h1>Siege interference test report</h1>
<table><tr><th>Date</th><td>{today}</td><th>Tool revision</th><td>{html.escape(rev)}</td></tr>
<tr><th>Test object</th><td colspan=3>Reference camera - detector - controller pipeline on QNX SDP 8.0</td></tr>
<tr><th>Environment</th><td colspan=3>{html.escape(target_text)}</td></tr>
<tr><th>Configuration</th><td colspan=3>deadline {deadline} ms, tolerance {tol:.1f}%, recovery budget {recovery} ms</td></tr>
<tr><th>Result</th><td colspan=3><b>{matched} of {len(cases)}</b> test cases matched their expected result</td></tr></table>
<p class="note"><b>Scope and status.</b> This document records evidence from stress tests of a stand-in pipeline on an emulator.
It is not a safety case, not a proof of freedom from interference, and not a certification claim.</p>
<h2>1. Pass criteria</h2><ol>{''.join(f'<li>{html.escape(t)}</li>' for t in CRITERIA)}</ol>
<h2>2. Requirements and traceability</h2><p>Derived requirements for this evaluation (not taken from a standard).</p>
<table>{tr(['Requirement','Statement','Test cases','Matched'],'th')}{reqhtml}</table>
<h2>3. Test cases</h2><table>{tr(['ID','Stimulus','Configuration','Runs','Failed (95% CI)','Expected','Observed','Result','Worst frame','Longest silence'],'th')}{rowshtml}</table>
<h2>4. Limits of this evidence</h2><ul>{''.join(f'<li>{html.escape(t)}</li>' for t in LIMITS)}</ul>
<h2>5. Review</h2><table>{tr(['Role','Name','Date','Signature'],'th')}{tr(['Author','','',''])}{tr(['Reviewer','','',''])}</table>
</body></html>"""
open(args.out + ".html", "w").write(page)
print(f"wrote {args.out}.md and {args.out}.html: {matched}/{len(cases)} test cases matched")
sys.exit(0)
