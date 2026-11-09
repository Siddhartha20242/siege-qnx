"""Shared logic for Siege's host tools: statistics, failure diagnosis, command building.

Kept free of I/O so it can be tested (tests/) and used by report.py, junit.py
and live.py alike.
"""

# The interference patterns documented in docs/patterns.md.
PATTERNS = {
    1: ("Priority starvation",
        "put the pipeline above its neighbours (prio), give it a CPU of its own (isolate), or cap the neighbour (budget)"),
    2: ("Queue-priority starvation",
        "raise the pipeline's priority above every client of the shared service; CPU isolation and CPU budgets do not help"),
    3: ("Burst interference",
        "keep inference-style jobs below the pipeline: prio, isolate and budget all work"),
    4: ("Same-priority timeslice jitter",
        "give the pipeline a higher priority than its neighbours, or relax a deadline that has no slack"),
    5: ("A dead service with no supervisor",
        "add a supervisor that restarts the stage; no scheduling profile can help"),
    6: ("Priority inversion through a shared lock",
        "use a priority-inheriting mutex (PTHREAD_PRIO_INHERIT) for every lock the pipeline shares; a higher pipeline priority does not help"),
}


def wilson(k, n, z=1.96):
    """95% Wilson score interval for k failures in n runs, as whole percentages."""
    if n == 0:
        return 0, 100
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return round(max(0.0, c - h) * 100), round(min(1.0, c + h) * 100)


def failure_rate(fails, n):
    return fails / n if n else 0.0


def observed_verdict(fails, n, max_fail_rate=0.2):
    """What a scenario did, in the CI gate's terms: 'pass' unless too many runs failed."""
    return "pass" if n and fails / n <= max_fail_rate else "fail"


def aggregate(runs):
    """Summarise a list of per-run results (None entries are runs that gave no result)."""
    ok = [r for r in runs if r]
    if not ok:
        return None
    ps = sorted(r["p50"] for r in ok)
    return dict(
        n=len(runs), fails=sum(1 for r in ok if r["fail"]) + (len(runs) - len(ok)),   # a run with no result counts as a failure, never as a pass
       
        p50=ps[len(ps) // 2], worst=max(r["max"] for r in ok),
        gap=max(r.get("max_gap_ms", 0) for r in ok), late=sum(r["late"] for r in ok),
        lost=sum(r["lost"] for r in ok), outages=sum(r.get("outages", 0) for r in ok),
        abandoned=sum(r.get("abandoned", 0) for r in ok))


def diagnose(atk, atk_prio, agg):
    """Which documented pattern a failing scenario most likely is, or None.

    Uses what the scenario did (its attacker and priority) together with the
    signature in the numbers. It is a hint, not a proof: see docs/patterns.md.
    """
    if not agg or agg["fails"] == 0:
        return None
    if agg["abandoned"] and atk in ("", None, "squat"):
        return 5        # a stage died (or its name was taken) and nothing replaced it
    if atk in ("flood", "workflood", "pipeflood"):
        return 2
    if atk == "ai":
        return 3
    if atk == "pinv":
        return 6
    if atk in ("cpu", "crash", "mem", "fd"):
        if atk_prio <= 10:
            return 4
        if agg["gap"] >= 1000 or agg["p50"] >= 100000:
            return 1
        return 3
    if agg["outages"] > 0 and agg["p50"] < 50000:
        return 2
    return None


def build_command(cfg, sc, profile, dur, ssh=False, deadline=None, tol=None, recovery=None):
    """The shell command that runs one scenario on the target, with its environment."""
    env = {"PROFILE": profile, "ATK": sc.get("attacker", ""), "ATK_PRIO": sc.get("prio", 10),
           "DEADLINE_MS": deadline if deadline is not None else cfg.get("deadline_ms", 15),
           "TOL_PM": tol if tol is not None else cfg.get("tolerance_permille", 20),
           "RECOVERY_MS": recovery if recovery is not None else cfg.get("recovery_ms", 500)}
    env.update(cfg.get("env", {}))
    if ssh:
        env["IDLE_POLL"] = 0
    profiles = cfg.get("profiles", [])
    if isinstance(profiles, dict):
        env.update(profiles.get(profile, {}))
    env.update(sc.get("env", {}))
    parts = [f'{k}="{v}"' if k == "ATK" else f"{k}={v}" for k, v in env.items()]
    external = cfg.get("pipeline", {}).get("command")
    if external:
        return " ".join(parts) + f" harness.sh {dur} " + external.format(dur=dur)
    return " ".join(parts) + f" pipeline.sh {dur}"
