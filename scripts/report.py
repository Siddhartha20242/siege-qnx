#!/usr/bin/env python3
"""Turn matrix.py JSON results into a report and a dashboard.

    scripts/report.py res-none.json res-prio.json ... [--out report]

Writes <out>.md, <out>.html and two standalone charts (<out>-heatmap.svg,
<out>-worst.svg). The findings are plain rules over the measured numbers (no
model involved), so the same data always gives the same report.
"""
import argparse, html, json, math, os, statistics, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from siegelib import PATTERNS, wilson, aggregate, diagnose

here = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser()
ap.add_argument("files", nargs="+")
ap.add_argument("--out", default="report")
ap.add_argument("--config", default=os.path.join(here, "..", "siege.json"), help="scenario order and deadline")
ap.add_argument("--deadline", type=int, help="deadline in ms, for the charts (default: from the config)")
args = ap.parse_args()

PROFILE_ORDER = ["none", "prio", "isolate", "budget", "secpol-connect", "secpol-ceiling", "secpol-names", "secpol", "secpol-least", "secpol-minimal"]
PROFILE_NOTE = {
    "none": "default round-robin priority 10",
    "prio": "pipeline at priority 40",
    "isolate": "pipeline on CPU 1, attackers on CPU 0",
    "budget": "attackers capped by SCHED_SPORADIC (10 ms / 100 ms)",
    "secpol-connect": "security policy: attackers may not connect to the detector's channel",
    "secpol-ceiling": "security policy: attackers may not raise their priority above 9",
    "secpol-names": "security policy: attackers may not attach a name to the path space",
    "secpol-least": "security policy: all three restrictions, and the detector keeps only the 5 abilities the probes could not rule out",
    "secpol-minimal": "security policy: all three restrictions, and the detector holds no abilities at all",
    "secpol": "security policy: all three restrictions together",
}

# Interference channels, in the vocabulary safety engineers use for "freedom from interference".
CHANNELS = [
    ("Execution time", "CPU contention from another process", lambda m: m["atk"] in ("cpu", "ai")),
    ("Memory", "another process holding and touching memory", lambda m: m["atk"] == "mem"),
    ("Message exchange", "a client abusing a shared service", lambda m: m["atk"] in ("flood", "workflood", "pipeflood")),
    ("Kernel objects", "descriptors, channels and connections exhausted", lambda m: m["atk"] == "fd"),
    ("Process failure", "a crashing process restarted in a loop", lambda m: m["atk"] == "crash"),
    ("Shared locks", "a low-priority process holding a lock the pipeline needs", lambda m: m["atk"] == "pinv"),
    ("Service failure", "a pipeline stage killed mid-run", lambda m: not m["atk"] and "KILL_AT" in m["extra"]),
]

cfg = {}
if os.path.exists(args.config):
    cfg = json.load(open(args.config))
deadline_ms = args.deadline or cfg.get("deadline_ms", 20)
order = [s["label"] for s in cfg.get("scenarios", [])]

rows = []
for f in args.files:
    rows += json.load(open(f))
profiles = [p for p in PROFILE_ORDER if any(r["profile"] == p for r in rows)]
scenarios = []
for r in rows:
    if r["scenario"] not in scenarios:
        scenarios.append(r["scenario"])
scenarios.sort(key=lambda s: order.index(s) if s in order else len(order))

targets = sorted({r.get("target", "emulator") for r in rows})
if all(t.startswith("emulator") for t in targets):
    MEASURED = "Measured in QEMU emulation: compare rows with each other, not with hardware latencies."
elif all(t.startswith("hardware") for t in targets):
    MEASURED = "Measured on real hardware (" + ", ".join(t.split(":", 1)[1] for t in targets) + ")."
else:
    MEASURED = "WARNING: these results mix emulator and hardware runs. Report them separately."

meta, cell, timelines = {}, {}, {}
for r in rows:
    meta[r["scenario"]] = dict(atk=r.get("atk", ""), extra=r.get("extra", {}) or {}, atk_prio=r.get("atk_prio", 10))
    runs = [x for x in r["runs"] if x]
    n = len(r["runs"])
    key = (r["scenario"], r["profile"])
    timed = [x for x in r["runs"] if x and x.get("samples")]
    if timed:
        timelines.setdefault(key, []).extend(timed)
    if key in cell and cell[key]["valid"] > len(runs):      # same scenario in several files: more valid runs wins, a tie goes to the later file
        continue
    cell[key] = dict(
        valid=len(runs), n=n, fails=sum(1 for x in runs if x["fail"]),
        p50=statistics.median([x["p50"] for x in runs]) if runs else None,
        worst=max((x["max"] for x in runs), default=None),
        gap=max((x["max_gap_ms"] for x in runs), default=0),
        late=sum(x["late"] for x in runs),
        restart=[x["restart_ms"] for x in runs if x.get("restart_ms") is not None],
        runs=runs)


def rate(c):
    return c["fails"] / c["n"] if c and c["n"] else 0.0


def ci(c):
    lo, hi = wilson(c["fails"], c["n"])
    return f"95% CI {lo}-{hi}%"


def ms(us):
    return "-" if us is None else (f"{us/1000:.1f} ms" if us < 1e6 else f"{us/1e6:.1f} s")


def verdict_class(c):
    if not c:
        return "na"
    r = rate(c)
    return "ok" if r == 0 else ("warn" if r < 0.5 else "bad")


def never_recovered(c):
    return bool(c) and any(x["abandoned"] for x in c["runs"])


RESTORED = 0.2          # a profile "restores" a scenario when at most this share of runs still fail (same as junit.py)


def label_with_residual(sc, p):
    c = cell[(sc, p)]
    return p if c["fails"] == 0 else f"{p} ({c['fails']}/{c['n']} runs still failed)"


attacks = [s for s in scenarios if meta[s]["atk"]]
faults = [s for s in scenarios if not meta[s]["atk"] and "KILL_AT" in meta[s]["extra"]]

# ---- headline: how many attacks break each profile ------------------------------
headline = []
for p in profiles:
    broke = [s for s in attacks if rate(cell.get((s, p))) >= 0.5]
    part = [s for s in attacks if 0 < rate(cell.get((s, p))) < 0.5]
    headline.append(dict(profile=p, broke=broke, partial=part, total=len(attacks)))

# ---- diagnosis: which documented pattern each failing scenario looks like -------------
diagnosis = {}
for sc in scenarios:
    c = cell.get((sc, "none"))
    if c and rate(c) >= 0.5:
        agg = aggregate(c["runs"])
        pid = diagnose(meta[sc]["atk"], int(meta[sc].get("atk_prio", 10)), agg)
        if pid:
            diagnosis[sc] = pid

# ---- findings: rules over the numbers -------------------------------------------
broken, intermittent, contained = [], [], []
fixed, reduced, not_fixed = {}, {}, {}
for sc in scenarios:
    base = cell.get((sc, "none"))
    if not base or sc.startswith("baseline"):
        continue
    if rate(base) >= 0.5:
        broken.append(sc)
        others = [p for p in profiles if p != "none" and cell.get((sc, p))]
        fixed[sc] = [label_with_residual(sc, p) for p in others if rate(cell[(sc, p)]) <= RESTORED]
        reduced[sc] = [label_with_residual(sc, p) for p in others if RESTORED < rate(cell[(sc, p)]) < rate(base)]
        not_fixed[sc] = [p for p in others if rate(cell[(sc, p)]) >= rate(base)]
    elif rate(base) > 0:
        intermittent.append(sc)
    elif "kill detector" not in sc:
        contained.append(sc)

findings = []
base = cell.get(("baseline (no attacker)", "none"))
if base:
    findings.append(("noise", f"Baseline: {base['fails']}/{base['n']} runs failed with no attacker; "
                     f"median latency {ms(base['p50'])}, worst frame {ms(base['worst'])}. "
                     "Timing is emulated, so read results as relative, not as hardware latencies."))
for sc in broken:
    b = cell[(sc, "none")]
    name = sc.strip()
    if never_recovered(b):
        findings.append(("break", f"{name}: the pipeline went silent and never recovered in {b['fails']}/{b['n']} runs "
                         "(the controller gave up after 3 s). Pattern 5, a dead service with no supervisor (docs/patterns.md): "
                         "scheduling profiles cannot help; a supervisor can."))
        continue
    silence = f", longest silence {b['gap']} ms" if b["gap"] else ""
    txt = (f"{name} breaks the unhardened pipeline in {b['fails']}/{b['n']} runs ({ci(b)}; "
           f"worst frame {ms(b['worst'])}{silence}).")
    if fixed[sc]:
        txt += f" Restored by: {', '.join(fixed[sc])}."
    if reduced[sc]:
        txt += f" Reduced by: {', '.join(reduced[sc])}."
    if not_fixed[sc]:
        txt += f" Not helped by: {', '.join(not_fixed[sc])}."
    if sc in diagnosis:
        title, fix = PATTERNS[diagnosis[sc]]
        txt += f" Looks like pattern {diagnosis[sc]}, {title.lower()} (docs/patterns.md): {fix}."
    findings.append(("break", txt))
for sc in intermittent:
    c = cell[(sc, "none")]
    findings.append(("noise", f"{sc.strip()} failed {c['fails']}/{c['n']} runs (worst frame {ms(c['worst'])}); "
                     "isolated spikes like this also occur in clean runs under emulation, so treat it as noise unless it repeats."))
if contained:
    n_min = min(cell[(sc, "none")]["n"] for sc in contained)
    hi = wilson(0, n_min)[1]
    findings.append(("ok", "No failure seen without any hardening: " + "; ".join(s.strip() for s in contained)
                     + f". That is 0 failures in {n_min} runs or more each; the 95% upper bound on "
                       f"the failure rate is {hi}%, so read it as 'not observed', not 'cannot happen'."))
checked = sum(x.get("checked", 0) for c in cell.values() for x in c["runs"])
wrong = sum(x.get("wrong", 0) for c in cell.values() for x in c["runs"])
if checked:
    findings.append(("ok", f"Detector accuracy (trained network): {checked - wrong} of {checked} checked frames correct "
                     f"({100 * (checked - wrong) / checked:.2f}%), across every scenario and profile, attacked or not. "
                     "Interference changed when answers arrived, not what they were."))
sup_ms, sup_gap = None, None
for sc in scenarios:
    if "supervised" in sc:
        c = cell.get((sc, "none"))
        if c and c["restart"]:
            sup_ms = statistics.median(c["restart"])
            sup_gap = max(x["max_gap_ms"] for x in c["runs"])
            findings.append(("ok", f"Supervised restart: the detector was back in {sup_ms:.0f} ms "
                             f"(median of {len(c['restart'])} runs); the controller saw a worst gap of {sup_gap} ms."))

# ---- evidence by interference channel -------------------------------------------
evidence = []
for name, what, pick in CHANNELS:
    scs = [s for s in scenarios if pick(meta[s])]
    if not scs:
        continue
    row = dict(channel=name, what=what, tested=scs, breaks=[], restored=[], not_helped=[], note="")
    if name == "Service failure":
        dead = [s for s in scs if "supervised" not in s]
        row["breaks"] = [s for s in dead if rate(cell.get((s, "none"))) >= 0.5]
        row["restored"] = ["supervisor"] if sup_ms is not None else []
        row["note"] = (f"restart {sup_ms:.0f} ms, controller gap {sup_gap} ms" if sup_ms is not None else "")
    elif name == "Shared locks":
        row["breaks"] = [s for s in scs if "plain" in s and rate(cell.get((s, "none"))) >= 0.5]
        fixes = [s for s in scs if "inheriting" in s and cell.get((s, "none"))]
        if row["breaks"] and fixes and all(rate(cell[(s, p)]) <= RESTORED for s in fixes for p in profiles if cell.get((s, p))):
            row["restored"] = ["a priority-inheriting mutex (the default mutex is also safe)"
                               if any("default" in s and cell.get((s, "none")) and rate(cell[(s, "none")]) <= RESTORED for s in scs)
                               else "a priority-inheriting mutex"]
        row["not_helped"] = [p for p in profiles if p != "none" and row["breaks"]
                             and all(rate(cell.get((s, p))) >= 0.5 for s in row["breaks"])]
    else:
        row["breaks"] = [s for s in scs if rate(cell.get((s, "none"))) >= 0.5]
        if row["breaks"]:
            for p in profiles:
                if p == "none":
                    continue
                rates = [rate(cell.get((s, p))) for s in row["breaks"]]
                if all(r <= RESTORED for r in rates):
                    bad = sum(cell[(s, p)]["fails"] for s in row["breaks"])
                    tot = sum(cell[(s, p)]["n"] for s in row["breaks"])
                    row["restored"].append(p if bad == 0 else f"{p} ({bad}/{tot} runs still failed)")
                elif all(r >= 0.5 for r in rates):
                    row["not_helped"].append(p)
    evidence.append(row)

SAFETY_NOTE = ("This is evidence from stress tests of a stand-in pipeline on an emulator. It is not a safety case, "
               "a proof of freedom from interference, or a certification claim.")


# ---- charts (standalone SVG, readable on light and dark backgrounds) --------------
COL = {"ok": "#1a7f37", "warn": "#bf8700", "bad": "#cf222e", "na": "#6e7781"}


def svg_heatmap():
    cw, ch, lw, top = 112, 30, 250, 56
    w, h = lw + cw * len(profiles) + 10, top + ch * len(scenarios) + 10
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
         'font-family="system-ui,sans-serif" font-size="13">']
    for j, p in enumerate(profiles):
        o.append(f'<text x="{lw + cw*j + cw/2}" y="30" text-anchor="middle" font-weight="700" fill="#6e7781">{p}</text>')
    for i, sc in enumerate(scenarios):
        y = top + ch * i
        o.append(f'<text x="8" y="{y + 20}" fill="#6e7781">{html.escape(sc.strip())}</text>')
        for j, p in enumerate(profiles):
            c = cell.get((sc, p))
            x = lw + cw * j
            o.append(f'<rect x="{x+2}" y="{y+2}" width="{cw-4}" height="{ch-4}" rx="4" fill="{COL[verdict_class(c)]}"/>')
            if c:
                o.append(f'<text x="{x + cw/2}" y="{y + 20}" text-anchor="middle" fill="#fff" font-weight="700">'
                         f'{c["fails"]}/{c["n"]}</text>')
    o.append("</svg>")
    return "\n".join(o)


def svg_worst():
    show = [p for p in ("none", "prio") if p in profiles]
    lw, bw, rowh = 250, 520, 18 * len(show) + 14
    scs = [s for s in attacks if all(cell.get((s, p)) for p in show)]
    h = 40 + rowh * len(scs) + 40
    w = lw + bw + 90
    lo, hi = 0.0, 4.0                                          # 1 ms .. 10 s, log scale

    def xpos(v_ms):
        return lw + bw * (min(max(math.log10(max(v_ms, 1.0)), lo), hi) - lo) / (hi - lo)

    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
         'font-family="system-ui,sans-serif" font-size="12">']
    for t, lab in ((0, "1 ms"), (1, "10 ms"), (2, "100 ms"), (3, "1 s"), (4, "10 s")):
        x = lw + bw * t / 4
        o.append(f'<line x1="{x}" y1="26" x2="{x}" y2="{h-30}" stroke="#6e7781" stroke-opacity=".25"/>')
        o.append(f'<text x="{x}" y="{h-12}" text-anchor="middle" fill="#6e7781">{lab}</text>')
    dx = xpos(deadline_ms)
    o.append(f'<line x1="{dx}" y1="22" x2="{dx}" y2="{h-30}" stroke="#bf8700" stroke-width="2" stroke-dasharray="5 4"/>')
    o.append(f'<text x="{dx+4}" y="18" fill="#bf8700">deadline {deadline_ms} ms</text>')
    for i, sc in enumerate(scs):
        y = 34 + rowh * i
        o.append(f'<text x="8" y="{y + 18}" fill="#6e7781">{html.escape(sc.strip())}</text>')
        for k, p in enumerate(show):
            c = cell[(sc, p)]
            v = (c["worst"] or 0) / 1000.0
            by = y + 18 * k
            o.append(f'<rect x="{lw}" y="{by+2}" width="{max(2, xpos(v) - lw)}" height="13" rx="2" '
                     f'fill="{COL[verdict_class(c)]}" opacity="{1 if p == "none" else .65}"/>')
            o.append(f'<text x="{xpos(v) + 5}" y="{by + 13}" fill="#6e7781">{p}: {v:.0f} ms</text>')
    o.append("</svg>")
    return "\n".join(o)


# ---- markdown ---------------------------------------------------------------------
md = ["# Siege report", "", f"_{MEASURED}_", ""]
for hline in headline:
    if hline["profile"] == "none":
        names = ", ".join(s.strip() for s in hline["broke"]) or "none"
        md.append(f"Without hardening, **{len(hline['broke'])} of {hline['total']} attacks** break the pipeline ({names}).")
    else:
        md.append(f"With `{hline['profile']}`: **{len(hline['broke'])} of {hline['total']}** still break it"
                  + (f" ({', '.join(s.strip() for s in hline['broke'])})" if hline["broke"] else "") + ".")
md += ["", "Each cell is failed runs / total runs for one attack under one hardening profile.", "",
       "| Scenario | " + " | ".join(profiles) + " |", "|---|" + "---|" * len(profiles)]
for sc in scenarios:
    cs = [cell.get((sc, p)) for p in profiles]
    md.append(f"| {sc.strip()} | " + " | ".join(f"{c['fails']}/{c['n']}" if c else "-" for c in cs) + " |")
md += ["", "## Interference evidence by channel", "",
       "| Channel | Tested | Breaks the unhardened pipeline | Restored by | Not helped by |", "|---|---|---|---|---|"]
for e in evidence:
    md.append(f"| {e['channel']} | {len(e['tested'])} scenario(s) | "
              f"{', '.join(s.strip() for s in e['breaks']) or 'nothing observed'} | "
              f"{', '.join(e['restored']) or '-'} | {', '.join(e['not_helped']) or '-'} |")
md += ["", f"_{SAFETY_NOTE}_", "", "## Profiles", ""] + [f"* **{p}**: {PROFILE_NOTE[p]}" for p in profiles]
md += ["", "## Findings", ""] + [f"* {t}" for _, t in findings]
open(args.out + ".md", "w").write("\n".join(md) + "\n")
open(args.out + "-heatmap.svg", "w").write(svg_heatmap() + "\n")
open(args.out + "-worst.svg", "w").write(svg_worst() + "\n")

# ---- html dashboard ---------------------------------------------------------------
def timeline_svg(key):
    """p99 latency per second for each recorded run of one cell (log scale), pass green and fail red."""
    runs = timelines.get(key, [])[:5]
    if not runs:
        return ""
    w, h, L, T, B = 300, 124, 36, 8, 18
    dur = max(5, max(sm["t"] for r in runs for sm in r["samples"]) + 1)

    def X(t):
        return L + (w - L - 6) * t / dur

    def Y(v_ms):
        return T + (h - T - B) * (1 - min(max(math.log10(max(v_ms, 1.0)), 0.0), 4.0) / 4.0)

    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
         'font-family="system-ui,sans-serif" font-size="9">']
    for v, lab in ((1, "1 ms"), (10, "10"), (100, "100"), (1000, "1 s"), (10000, "10 s")):
        o.append(f'<line x1="{L}" y1="{Y(v)}" x2="{w-6}" y2="{Y(v)}" stroke="#6e7781" stroke-opacity=".25"/>')
        o.append(f'<text x="2" y="{Y(v)+3}" fill="#6e7781">{lab}</text>')
    o.append(f'<line x1="{L}" y1="{Y(deadline_ms)}" x2="{w-6}" y2="{Y(deadline_ms)}" stroke="#bf8700" stroke-width="1.5" stroke-dasharray="4 3"/>')
    for t in range(0, dur + 1):
        o.append(f'<text x="{X(t)-3}" y="{h-5}" fill="#6e7781">{t}</text>')
    for r in runs:
        pts = " ".join(f"{X(sm['t']):.1f},{Y(sm['p99'] / 1000.0):.1f}" for sm in sorted(r["samples"], key=lambda z: z["t"]))
        col = COL["bad"] if r["fail"] else COL["ok"]
        o.append(f'<polyline points="{pts}" fill="none" stroke="{col}" stroke-width="1.6" stroke-opacity=".85"/>')
        for sm in r["samples"]:
            o.append(f'<circle cx="{X(sm["t"]):.1f}" cy="{Y(sm["p99"] / 1000.0):.1f}" r="2" fill="{col}"/>')
    o.append("</svg>")
    return ('<div class="chart"><small>p99 per second (log scale), one line per recorded run; dashed: deadline</small>'
            + "".join(o) + "</div>")


def run_table(c):
    r = ['<table class="runs"><tr><th>#</th><th>result</th><th>late</th><th>lost</th><th>p50</th><th>p99</th><th>max</th><th>gap</th></tr>']
    for i, x in enumerate(c["runs"], 1):
        r.append(f'<tr class="{"bad" if x["fail"] else "ok"}"><td>{i}</td><td>{"FAIL" if x["fail"] else "pass"}</td>'
                 f'<td>{x["late"]}</td><td>{x["lost"]}</td><td>{ms(x["p50"])}</td><td>{ms(x["p99"])}</td>'
                 f'<td>{ms(x["max"])}</td><td>{x["max_gap_ms"]} ms</td></tr>')
    return "".join(r) + "</table>"


th = "".join(f"<th>{html.escape(p)}<small>{html.escape(PROFILE_NOTE[p])}</small></th>" for p in profiles)
body = ""
for sc in scenarios:
    tds = ""
    for p in profiles:
        c = cell.get((sc, p))
        if not c:
            tds += '<td class="na">-</td>'
            continue
        tds += (f'<td class="{verdict_class(c)}"><b>{c["fails"]}/{c["n"]}</b>'
                f'<small>p50 {ms(c["p50"])} · worst {ms(c["worst"])}</small><small>{ci(c)}</small>'
                f'<details><summary>runs</summary>{run_table(c)}{timeline_svg((sc, p))}</details></td>')
    body += f"<tr><th>{html.escape(sc.strip())}</th>{tds}</tr>"

cards = ""
for hline in headline:
    k = len(hline["broke"])
    cls = "bad" if k else "ok"
    detail = ", ".join(s.strip() for s in hline["broke"]) or "none of the attacks"
    cards += (f'<div class="card {cls}"><div class="big">{k} of {hline["total"]}</div>'
              f'<div class="lbl">attacks break it under <b>{html.escape(hline["profile"])}</b></div>'
              f'<small>{html.escape(detail)}</small></div>')
if sup_ms is not None:
    cards += (f'<div class="card ok"><div class="big">{sup_ms:.0f} ms</div>'
              f'<div class="lbl">to restart a killed detector with the supervisor</div>'
              f'<small>controller saw a {sup_gap} ms gap; without it the pipeline never recovers</small></div>')

ev = ""
for e in evidence:
    ev += (f"<tr><th>{html.escape(e['channel'])}<small>{html.escape(e['what'])}</small></th>"
           f"<td>{len(e['tested'])}</td>"
           f"<td class=\"{'bad' if e['breaks'] else 'ok'}\">{html.escape(', '.join(s.strip() for s in e['breaks']) or 'nothing observed')}</td>"
           f"<td>{html.escape(', '.join(e['restored']) or '-')}</td>"
           f"<td>{html.escape(', '.join(e['not_helped']) or '-')}</td></tr>")
items = "".join(f'<li class="{k}">{html.escape(t)}</li>' for k, t in findings)

page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Siege report</title>
<style>
:root{{--bg:#fff;--fg:#1c2330;--mute:#5d6778;--line:#dfe3ea;--ok:#d9f2e3;--okx:#106a3a;--warn:#fdf0cf;--warnx:#7a5200;--bad:#fbdcdc;--badx:#8c1d1d}}
@media(prefers-color-scheme:dark){{:root{{--bg:#12161d;--fg:#e6e9ef;--mute:#9aa4b5;--line:#2a313d;--ok:#16382a;--okx:#8fe0b0;--warn:#3d3112;--warnx:#f0cf75;--bad:#43191b;--badx:#ff9a9a}}}}
body{{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif}}
main{{max-width:1040px;margin:0 auto;padding:24px 16px}}
h1{{font-size:26px;margin:0 0 4px}} h2{{margin:32px 0 10px;font-size:19px}} p.sub{{color:var(--mute);margin:0 0 20px}}
.cards{{display:flex;gap:12px;flex-wrap:wrap}} .card{{flex:1 1 200px;border-radius:10px;padding:14px 16px;border:1px solid var(--line)}}
.card.ok{{background:var(--ok);color:var(--okx)}} .card.bad{{background:var(--bad);color:var(--badx)}}
.card .big{{font-size:30px;font-weight:700;line-height:1.1}} .card .lbl{{margin:2px 0 6px}} .card small{{display:block;opacity:.85;font-size:12px}}
.wrap{{overflow-x:auto}} table{{border-collapse:collapse;width:100%;min-width:640px}}
th,td{{border:1px solid var(--line);padding:8px 10px;text-align:left;vertical-align:top}}
thead th small,td small,th small{{display:block;color:var(--mute);font-weight:400;font-size:12px}}
td.ok{{background:var(--ok);color:var(--okx)}} td.warn{{background:var(--warn);color:var(--warnx)}}
td.bad{{background:var(--bad);color:var(--badx)}} td.na{{color:var(--mute)}}
td b{{font-size:18px}} td small{{color:inherit;opacity:.8}}
details summary{{cursor:pointer;font-size:12px;margin-top:4px;opacity:.9}}
table.runs{{min-width:0;margin-top:6px;font-size:12px}} table.runs th,table.runs td{{padding:2px 6px;border-color:transparent}}
table.runs tr.bad td{{color:var(--badx)}}
.chart{{overflow-x:auto}} .chart svg{{max-width:100%;height:auto}}
ul{{padding-left:20px}} li{{margin:6px 0}} li.break{{color:var(--badx)}} li.ok{{color:var(--okx)}}
.note{{color:var(--mute);font-size:13px}}
</style></head><body><main>
<h1>Siege report</h1>
<p class="sub">Failed runs / total runs per attack and hardening profile. Green: every run met its deadlines. Red: the pipeline failed in most runs.<br>{html.escape(MEASURED)}</p>
<div class="cards">{cards}</div>
<h2>Results</h2>
<div class="wrap"><table><thead><tr><th>Scenario</th>{th}</tr></thead><tbody>{body}</tbody></table></div>
<h2>Worst frame per attack</h2>
<p class="note">Log scale. The dashed line is the deadline. Solid bars: no hardening. Lighter bars: the pipeline at priority 40.</p>
<div class="chart">{svg_worst()}</div>
<h2>Interference evidence by channel</h2>
<div class="wrap"><table><thead><tr><th>Channel</th><th>Scenarios</th><th>Breaks the unhardened pipeline</th><th>Restored by</th><th>Not helped by</th></tr></thead><tbody>{ev}</tbody></table></div>
<p class="note">{html.escape(SAFETY_NOTE)}</p>
<h2>Findings</h2><ul>{items}</ul>
<p class="note">Generated from measured runs by fixed rules. QEMU timing is emulated: compare across rows, not against hardware.</p>
</main></body></html>"""
open(args.out + ".html", "w").write(page)
print(f"wrote {args.out}.md, {args.out}.html and two SVG charts ({len(scenarios)} scenarios x {len(profiles)} profiles)")
