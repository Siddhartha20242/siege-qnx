#!/usr/bin/env python3
"""Turn matrix.py JSON results into a report and a dashboard.

    scripts/report.py res-none.json res-prio.json ... [--out report]

Writes <out>.md and <out>.html. The findings are plain rules over the measured
numbers (no model involved), so the same data always gives the same report.
"""
import argparse, html, json, statistics, sys

ap = argparse.ArgumentParser()
ap.add_argument("files", nargs="+")
ap.add_argument("--out", default="report")
args = ap.parse_args()

PROFILE_ORDER = ["none", "prio", "isolate", "budget"]
PROFILE_NOTE = {
    "none": "default round-robin priority 10",
    "prio": "pipeline at priority 40",
    "isolate": "pipeline on CPU 1, attackers on CPU 0",
    "budget": "attackers capped by SCHED_SPORADIC (10 ms / 100 ms)",
}

rows = []                                   # one entry per (profile, scenario)
for f in args.files:
    rows += json.load(open(f))
profiles = [p for p in PROFILE_ORDER if any(r["profile"] == p for r in rows)]
scenarios = []
for r in rows:
    if r["scenario"] not in scenarios:
        scenarios.append(r["scenario"])

cell = {}                                   # (scenario, profile) -> summary
for r in rows:
    runs = [x for x in r["runs"] if x]
    n = len(r["runs"])
    cell[(r["scenario"], r["profile"])] = dict(
        n=n, fails=sum(1 for x in runs if x["fail"]),
        p50=statistics.median([x["p50"] for x in runs]) if runs else None,
        worst=max((x["max"] for x in runs), default=None),
        gap=max((x["max_gap_ms"] for x in runs), default=0),
        late=sum(x["late"] for x in runs),
        restart=[x["restart_ms"] for x in runs if x.get("restart_ms") is not None],
        outage=[x["outage_ms"] for x in runs if x.get("outage_ms") is not None],
        runs=runs)

def rate(c):
    return c["fails"] / c["n"] if c and c["n"] else 0.0

def ms(us):
    return "-" if us is None else (f"{us/1000:.1f} ms" if us < 1e6 else f"{us/1e6:.1f} s")

# ---- findings: rules over the numbers -----------------------------------------
broken, contained, fixed_by, unfixed = [], [], {}, []
for sc in scenarios:
    base = cell.get((sc, "none"))
    if not base or sc.startswith("baseline"):
        continue
    if rate(base) >= 0.5:
        broken.append(sc)
        fixes = [p for p in profiles if p != "none" and rate(cell.get((sc, p))) == 0
                 and cell.get((sc, p))]
        fixed_by[sc] = fixes
        if not fixes:
            unfixed.append(sc)
    elif rate(base) == 0 and "kill detector" not in sc:
        contained.append(sc)

findings = []
base = cell.get(("baseline (no attacker)", "none"))
if base:
    findings.append(("noise", f"Baseline: {base['fails']}/{base['n']} runs failed with no attacker; "
                     f"median latency {ms(base['p50'])}, worst frame {ms(base['worst'])}. "
                     "Timing is emulated, so read results as relative, not as hardware latencies."))
for sc in broken:
    b = cell[(sc, "none")]
    fx = fixed_by[sc]
    txt = (f"{sc.strip()} breaks the unhardened pipeline in {b['fails']}/{b['n']} runs "
           f"(worst frame {ms(b['worst'])}, longest silence {b['gap']} ms).")
    txt += (f" Restored by: {', '.join(fx)}." if fx else " No profile restored it.")
    findings.append(("break", txt))
if contained:
    findings.append(("ok", "Contained by QNX without any hardening (0 failed runs): "
                     + "; ".join(s.strip() for s in contained) + "."))
for sc in scenarios:
    if "supervised" in sc:
        c = cell.get((sc, "none"))
        if c and c["restart"]:
            gaps = [x["max_gap_ms"] for x in c["runs"]]
            findings.append(("ok", f"Supervised restart: the detector was back in "
                             f"{statistics.median(c['restart']):.0f} ms (median of {len(c['restart'])} runs); "
                             f"the controller saw a worst gap of {max(gaps)} ms."))
    if "no supervisor" in sc:
        c = cell.get((sc, "none"))
        if c:
            findings.append(("break", f"Without a supervisor a killed detector is never replaced: "
                             f"{c['fails']}/{c['n']} runs failed."))

# ---- markdown ------------------------------------------------------------------
md = ["# Siege report", "",
      "Each cell is failed runs / total runs for one attack under one hardening profile.", ""]
md.append("| Scenario | " + " | ".join(profiles) + " |")
md.append("|---|" + "---|" * len(profiles))
for sc in scenarios:
    cs = [cell.get((sc, p)) for p in profiles]
    md.append(f"| {sc.strip()} | " + " | ".join(f"{c['fails']}/{c['n']}" if c else "-" for c in cs) + " |")
md += ["", "## Profiles", ""] + [f"* **{p}**: {PROFILE_NOTE[p]}" for p in profiles]
md += ["", "## Findings", ""] + [f"* {t}" for _, t in findings]
open(args.out + ".md", "w").write("\n".join(md) + "\n")

# ---- html dashboard -------------------------------------------------------------
def cls(c):
    if not c: return "na"
    r = rate(c)
    return "ok" if r == 0 else ("warn" if r < 0.5 else "bad")

th = "".join(f"<th>{html.escape(p)}<small>{html.escape(PROFILE_NOTE[p])}</small></th>" for p in profiles)
body = ""
for sc in scenarios:
    tds = ""
    for p in profiles:
        c = cell.get((sc, p))
        tds += (f'<td class="{cls(c)}"><b>{c["fails"]}/{c["n"]}</b>'
                f'<small>p50 {ms(c["p50"])} · worst {ms(c["worst"])}</small></td>') if c else '<td class="na">-</td>'
    body += f"<tr><th>{html.escape(sc.strip())}</th>{tds}</tr>"
items = "".join(f'<li class="{k}">{html.escape(t)}</li>' for k, t in findings)

page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Siege report</title>
<style>
:root{{--bg:#fff;--fg:#1c2330;--mute:#5d6778;--line:#dfe3ea;--ok:#d9f2e3;--okx:#106a3a;--warn:#fdf0cf;--warnx:#7a5200;--bad:#fbdcdc;--badx:#8c1d1d}}
@media(prefers-color-scheme:dark){{:root{{--bg:#12161d;--fg:#e6e9ef;--mute:#9aa4b5;--line:#2a313d;--ok:#16382a;--okx:#8fe0b0;--warn:#3d3112;--warnx:#f0cf75;--bad:#43191b;--badx:#ff9a9a}}}}
body{{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif}}
main{{max-width:980px;margin:0 auto;padding:24px 16px}}
h1{{font-size:24px;margin:0 0 4px}} p.sub{{color:var(--mute);margin:0 0 20px}}
.wrap{{overflow-x:auto}} table{{border-collapse:collapse;width:100%;min-width:640px}}
th,td{{border:1px solid var(--line);padding:8px 10px;text-align:left;vertical-align:top}}
thead th small,td small{{display:block;color:var(--mute);font-weight:400;font-size:12px}}
td.ok{{background:var(--ok);color:var(--okx)}} td.warn{{background:var(--warn);color:var(--warnx)}}
td.bad{{background:var(--bad);color:var(--badx)}} td.na{{color:var(--mute)}}
td b{{font-size:18px}} td small{{color:inherit;opacity:.8}}
ul{{padding-left:20px}} li{{margin:6px 0}} li.break{{color:var(--badx)}} li.ok{{color:var(--okx)}}
</style></head><body><main>
<h1>Siege report</h1>
<p class="sub">Failed runs / total runs per attack and hardening profile. Green: all runs met their deadlines. Red: the pipeline failed in most runs.</p>
<div class="wrap"><table><thead><tr><th>Scenario</th>{th}</tr></thead><tbody>{body}</tbody></table></div>
<h2>Findings</h2><ul>{items}</ul>
<p class="sub">Generated from measured runs by fixed rules. QEMU timing is emulated: compare across rows, not against hardware.</p>
</main></body></html>"""
open(args.out + ".html", "w").write(page)
print(f"wrote {args.out}.md and {args.out}.html ({len(scenarios)} scenarios x {len(profiles)} profiles)")
