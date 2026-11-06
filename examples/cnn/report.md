# Siege report

_Measured in QEMU emulation: compare rows with each other, not with hardware latencies._

Without hardening, **3 of 5 attacks** break the pipeline (cpu hog   @prio 20, workflood @prio 30, AI neighbour@prio 20).
With `prio`: **0 of 5** still break it.
With `isolate`: **1 of 5** still break it (workflood @prio 30).
With `budget`: **1 of 5** still break it (workflood @prio 30).

Each cell is failed runs / total runs for one attack under one hardening profile.

| Scenario | none | prio | isolate | budget |
|---|---|---|---|---|
| baseline (no attacker) | 0/5 | 1/5 | 0/5 | 0/5 |
| cpu hog   @prio 20 | 5/5 | 0/5 | 0/5 | 0/5 |
| workflood @prio 30 | 5/5 | 1/5 | 5/5 | 4/5 |
| AI neighbour@prio 10 | 0/5 | 1/5 | 0/5 | 0/5 |
| AI neighbour@prio 20 | 5/5 | 0/5 | 0/5 | 0/5 |
| mem hog   @prio 10 | 0/5 | 0/5 | 0/5 | 0/5 |
| kill detector, no supervisor | 5/5 | 5/5 | 5/5 | 5/5 |
| kill detector, supervised | 0/5 | 0/5 | 1/5 | 0/5 |

## Interference evidence by channel

| Channel | Tested | Breaks the unhardened pipeline | Restored by | Not helped by |
|---|---|---|---|---|
| Execution time | 3 scenario(s) | cpu hog   @prio 20, AI neighbour@prio 20 | prio, isolate, budget | - |
| Memory | 1 scenario(s) | nothing observed | - | - |
| Message exchange | 1 scenario(s) | workflood @prio 30 | prio (1/5 runs still failed) | isolate, budget |
| Service failure | 2 scenario(s) | kill detector, no supervisor | supervisor | - |

_This is evidence from stress tests of a stand-in pipeline on an emulator. It is not a safety case, a proof of freedom from interference, or a certification claim._

## Profiles

* **none**: default round-robin priority 10
* **prio**: pipeline at priority 40
* **isolate**: pipeline on CPU 1, attackers on CPU 0
* **budget**: attackers capped by SCHED_SPORADIC (10 ms / 100 ms)

## Findings

* Baseline: 0/5 runs failed with no attacker; median latency 2.9 ms, worst frame 27.5 ms. Timing is emulated, so read results as relative, not as hardware latencies.
* cpu hog   @prio 20 breaks the unhardened pipeline in 5/5 runs (95% CI 57-100%; worst frame 5.0 s, longest silence 5009 ms). Restored by: prio, isolate, budget. Looks like pattern 1, priority starvation (docs/patterns.md): put the pipeline above its neighbours (prio), give it a CPU of its own (isolate), or cap the neighbour (budget).
* workflood @prio 30 breaks the unhardened pipeline in 5/5 runs (95% CI 57-100%; worst frame 16.8 ms, longest silence 381 ms). Restored by: prio (1/5 runs still failed). Reduced by: budget (4/5 runs still failed). Not helped by: isolate. Looks like pattern 2, queue-priority starvation (docs/patterns.md): raise the pipeline's priority above every client of the shared service; CPU isolation and CPU budgets do not help.
* AI neighbour@prio 20 breaks the unhardened pipeline in 5/5 runs (95% CI 57-100%; worst frame 45.9 ms, longest silence 62 ms). Restored by: prio, isolate, budget. Looks like pattern 3, burst interference (docs/patterns.md): keep inference-style jobs below the pipeline: prio, isolate and budget all work.
* kill detector, no supervisor: the pipeline went silent and never recovered in 5/5 runs (the controller gave up after 3 s). Pattern 5, a dead service with no supervisor (docs/patterns.md): scheduling profiles cannot help; a supervisor can.
* No failure seen without any hardening: AI neighbour@prio 10; mem hog   @prio 10. That is 0 failures in 5 runs or more each; the 95% upper bound on the failure rate is 43%, so read it as 'not observed', not 'cannot happen'.
* Detector accuracy (trained network): 35544 of 35544 checked frames correct (100.00%), across every scenario and profile, attacked or not. Interference changed when answers arrived, not what they were.
* Supervised restart: the detector was back in 5 ms (median of 5 runs); the controller saw a worst gap of 40 ms.
