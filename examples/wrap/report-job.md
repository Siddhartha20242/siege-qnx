# Siege report

_Measured in QEMU emulation: compare rows with each other, not with hardware latencies._

Without hardening, **3 of 3 attacks** break the pipeline (cpu hog   @prio 10, cpu hog   @prio 20, crash loop@prio 20).
With `prio`: **0 of 3** still break it.

Each cell is failed runs / total runs for one attack under one hardening profile.

| Scenario | none | prio |
|---|---|---|
| baseline (no attacker) | 1/5 | 0/5 |
| cpu hog   @prio 10 | 5/5 | 0/5 |
| cpu hog   @prio 20 | 5/5 | 0/5 |
| crash loop@prio 20 | 5/5 | 0/5 |

## Interference evidence by channel

| Channel | Tested | Breaks the unhardened pipeline | Restored by | Not helped by |
|---|---|---|---|---|
| Execution time | 2 scenario(s) | cpu hog   @prio 10, cpu hog   @prio 20 | prio | - |
| Process failure | 1 scenario(s) | crash loop@prio 20 | prio | - |

_This is evidence from stress tests of a stand-in pipeline on an emulator. It is not a safety case, a proof of freedom from interference, or a certification claim._

## Profiles

* **none**: default round-robin priority 10
* **prio**: pipeline at priority 40

## Findings

* Baseline: 1/5 runs failed with no attacker; median latency 1.5 ms, worst frame 39.1 ms. Timing is emulated, so read results as relative, not as hardware latencies.
* cpu hog   @prio 10 breaks the unhardened pipeline in 5/5 runs (95% CI 57-100%; worst frame 1.4 s). Restored by: prio. Looks like pattern 4, same-priority timeslice jitter (docs/patterns.md): give the pipeline a higher priority than its neighbours, or relax a deadline that has no slack.
* cpu hog   @prio 20 breaks the unhardened pipeline in 5/5 runs (95% CI 57-100%; worst frame 8.0 s). Restored by: prio. Looks like pattern 1, priority starvation (docs/patterns.md): put the pipeline above its neighbours (prio), give it a CPU of its own (isolate), or cap the neighbour (budget).
* crash loop@prio 20 breaks the unhardened pipeline in 5/5 runs (95% CI 57-100%; worst frame 27.8 ms). Restored by: prio. Looks like pattern 3, burst interference (docs/patterns.md): keep inference-style jobs below the pipeline: prio, isolate and budget all work.
