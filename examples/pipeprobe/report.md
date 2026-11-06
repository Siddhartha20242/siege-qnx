# Siege report

_Measured in QEMU emulation: compare rows with each other, not with hardware latencies._

Without hardening, **2 of 3 attacks** break the pipeline (pipe flood @prio 30, cpu hog   @prio 20).
With `prio`: **0 of 3** still break it.

Each cell is failed runs / total runs for one attack under one hardening profile.

| Scenario | none | prio |
|---|---|---|
| baseline (no attacker) | 0/5 | 0/5 |
| pipe flood @prio 10 | 0/5 | 0/5 |
| pipe flood @prio 30 | 5/5 | 0/5 |
| cpu hog   @prio 20 | 5/5 | 0/5 |

## Interference evidence by channel

| Channel | Tested | Breaks the unhardened pipeline | Restored by | Not helped by |
|---|---|---|---|---|
| Execution time | 1 scenario(s) | cpu hog   @prio 20 | prio | - |
| Message exchange | 2 scenario(s) | pipe flood @prio 30 | prio | - |

_This is evidence from stress tests of a stand-in pipeline on an emulator. It is not a safety case, a proof of freedom from interference, or a certification claim._

## Profiles

* **none**: default round-robin priority 10
* **prio**: pipeline at priority 40

## Findings

* Baseline: 0/5 runs failed with no attacker; median latency 1.8 ms, worst frame 16.5 ms. Timing is emulated, so read results as relative, not as hardware latencies.
* pipe flood @prio 30 breaks the unhardened pipeline in 5/5 runs (95% CI 57-100%; worst frame 913.3 ms). Restored by: prio. Looks like pattern 2, queue-priority starvation (docs/patterns.md): raise the pipeline's priority above every client of the shared service; CPU isolation and CPU budgets do not help.
* cpu hog   @prio 20 breaks the unhardened pipeline in 5/5 runs (95% CI 57-100%; worst frame 5.0 s). Restored by: prio. Looks like pattern 1, priority starvation (docs/patterns.md): put the pipeline above its neighbours (prio), give it a CPU of its own (isolate), or cap the neighbour (budget).
* No failure seen without any hardening: pipe flood @prio 10. That is 0 failures in 5 runs or more each; the 95% upper bound on the failure rate is 43%, so read it as 'not observed', not 'cannot happen'.
