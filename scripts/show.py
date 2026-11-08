#!/usr/bin/env python3
"""Show saved results in the terminal, with nothing installed: no QNX, no QEMU, no VM.

    ./siege show                  the main measured matrix (every attack against every hardening profile)
    ./siege show secpol           the QNX security-policy runs (examples/secpol/results)
    ./siege show FILE.json ...    any result files written by ./siege test --json
    ./siege show --open           also open the full HTML report in a browser

Each cell is failed runs out of total. A cell with no failures is green, all runs failed is red,
anything in between is yellow, because that is a flaky outcome and the count matters.
"""
import argparse, glob, json, os, subprocess, sys, webbrowser

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
G, R, Y, B, D, X = "\033[32m", "\033[31m", "\033[33m", "\033[1m", "\033[2m", "\033[0m"
ORDER = ["none", "prio", "isolate", "budget", "secpol-connect", "secpol-ceiling", "secpol-names", "secpol", "secpol-least", "secpol-minimal"]


def main_files():
    out = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "results_files.py")], capture_output=True, text=True)
    return out.stdout.split()


def load(files):
    """{scenario: {profile: (failed, total)}}, in first-seen scenario order; later files win."""
    table, order = {}, []
    for f in files:
        try:
            data = json.load(open(f))
        except (OSError, ValueError):
            sys.exit(f"show: cannot read {f} as JSON")
        if not isinstance(data, list):
            continue
        for e in data:
            if not isinstance(e, dict) or "runs" not in e or "scenario" not in e:
                continue
            runs = [r for r in e["runs"] if isinstance(r, dict) and "fail" in r]
            if not runs:
                continue
            if e["scenario"] not in table:
                table[e["scenario"]] = {}
                order.append(e["scenario"])
            table[e["scenario"]][e["profile"]] = (sum(bool(r["fail"]) for r in runs), len(runs))
    return table, order


def render(table, order, color=True):
    profiles = [p for p in ORDER if any(p in row for row in table.values())]
    profiles += sorted({p for row in table.values() for p in row} - set(profiles))
    w = max([len(s) for s in order] + [8])
    cw = [max(len(p), 7) for p in profiles]

    def paint(text, code):
        return f"{code}{text}{X}" if color else text

    lines = [paint("scenario".ljust(w), B) + "  " + "  ".join(paint(p.rjust(c), B) for p, c in zip(profiles, cw))]
    for s in order:
        cells = []
        for p, c in zip(profiles, cw):
            if p not in table[s]:
                cells.append(paint("-".rjust(c), D))
                continue
            f, n = table[s][p]
            cells.append(paint(f"{f}/{n}".rjust(c), G if f == 0 else R if f == n else Y))
        lines.append(s.ljust(w) + "  " + "  ".join(cells))
    return "\n".join(lines)


LEGEND = {
    "none": "no hardening", "prio": "pipeline outranks its neighbours", "isolate": "pipeline on its own CPU",
    "budget": "neighbours capped by a CPU budget",
    "secpol-connect": "policy: attacker may not send to the detector", "secpol-ceiling": "policy: attacker may not raise its priority past 9",
    "secpol-names": "policy: attacker may not register a service name", "secpol": "policy: all three at once",
    "secpol-least": "all three, and the detector keeps only 5 abilities", "secpol-minimal": "all three, and the detector keeps no abilities",
}


def main():
    ap = argparse.ArgumentParser(description="show saved Siege results in the terminal")
    ap.add_argument("what", nargs="*", help="'secpol', or result JSON files; default is the main matrix")
    ap.add_argument("--open", action="store_true", help="open docs/report.html in a browser")
    ap.add_argument("--no-color", action="store_true")
    a = ap.parse_args()

    if a.what == ["secpol"]:
        files = sorted(glob.glob(os.path.join(ROOT, "examples", "secpol", "results", "*.json")))
        title = "QNX security policy (a policy is pushed into the kernel; see docs/security-policy.md)"
    elif a.what:
        files, title = a.what, "your result files"
    else:
        files = main_files()
        title = "main matrix: each attack against each hardening profile (emulated QNX 8.0)"
    table, order = load(files)
    if not table:
        sys.exit("show: no scenario results found. Run ./siege test --json out.json first, or ./siege show with no arguments.")
    color = sys.stdout.isatty() and not a.no_color
    print(f"{B if color else ''}{title}{X if color else ''}")
    print("failed runs / total runs; green = none failed, red = all failed, yellow = flaky\n")
    print(render(table, order, color))
    used = [p for p in ORDER if any(p in row for row in table.values())]
    print("\n" + "\n".join(f"  {p:15} {LEGEND[p]}" for p in used))
    report = os.path.join(ROOT, "docs", "report.html")
    print(f"\nFull report with intervals and charts: {os.path.relpath(report)}  (./siege show --open)")
    if a.open:
        webbrowser.open("file://" + os.path.abspath(report))


if __name__ == "__main__":
    main()
