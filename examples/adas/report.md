# Siege report

_Measured in QEMU emulation: compare rows with each other, not with hardware latencies._

Without hardening, **3 of 7 attacks** break the pipeline (QM cpu load @prio 20, QM perception neighbour @prio 20, QM client floods shared detector @prio 30).
With `prio`: **0 of 7** still break it.
With `isolate`: **1 of 7** still break it (QM client floods shared detector @prio 30).
With `budget`: **1 of 7** still break it (QM client floods shared detector @prio 30).

Each cell is failed runs / total runs for one attack under one hardening profile.

| Scenario | none | prio | isolate | budget |
|---|---|---|---|---|
| baseline (no QM load) | 0/5 | 0/5 | 0/5 | 0/5 |
| QM cpu load @prio 10 | 0/5 | 0/5 | 0/5 | 0/5 |
| QM cpu load @prio 20 | 5/5 | 0/5 | 0/5 | 0/5 |
| QM perception neighbour @prio 20 | 5/5 | 0/5 | 0/5 | 0/5 |
| QM client floods shared detector @prio 30 | 5/5 | 0/5 | 5/5 | 5/5 |
| QM memory load @prio 10 | 0/5 | 0/5 | 0/5 | 0/5 |
| QM service crash loop @prio 20 | 0/5 | 0/5 | 0/5 | 0/5 |
| lock shared with QM task (default mutex) | 0/5 | 0/5 | 0/5 | 0/5 |
| detector killed, supervised | 0/5 | 0/5 | 0/5 | 0/5 |

## Interference evidence by channel

| Channel | Tested | Breaks the unhardened pipeline | Restored by | Not helped by |
|---|---|---|---|---|
| Execution time | 3 scenario(s) | QM cpu load @prio 20, QM perception neighbour @prio 20 | prio, isolate, budget | - |
| Memory | 1 scenario(s) | nothing observed | - | - |
| Message exchange | 1 scenario(s) | QM client floods shared detector @prio 30 | prio | isolate, budget |
| Process failure | 1 scenario(s) | nothing observed | - | - |
| Shared locks | 1 scenario(s) | nothing observed | - | - |
| Service failure | 1 scenario(s) | nothing observed | supervisor | - |

_This is evidence from stress tests of a stand-in pipeline on an emulator. It is not a safety case, a proof of freedom from interference, or a certification claim._

## Profiles

* **none**: default round-robin priority 10
* **prio**: pipeline at priority 40
* **isolate**: pipeline on CPU 1, attackers on CPU 0
* **budget**: attackers capped by SCHED_SPORADIC (10 ms / 100 ms)

## Findings

* QM cpu load @prio 20: the pipeline went silent and never recovered in 5/5 runs (the controller gave up after 3 s). Pattern 5, a dead service with no supervisor (docs/patterns.md): scheduling profiles cannot help; a supervisor can.
* QM perception neighbour @prio 20 breaks the unhardened pipeline in 5/5 runs (95% CI 57-100%; worst frame 43.2 ms, longest silence 74 ms). Restored by: prio, isolate, budget. Looks like pattern 3, burst interference (docs/patterns.md): keep inference-style jobs below the pipeline: prio, isolate and budget all work.
* QM client floods shared detector @prio 30 breaks the unhardened pipeline in 5/5 runs (95% CI 57-100%; worst frame 15.6 ms, longest silence 1255 ms). Restored by: prio. Not helped by: isolate, budget. Looks like pattern 2, queue-priority starvation (docs/patterns.md): raise the pipeline's priority above every client of the shared service; CPU isolation and CPU budgets do not help.
* No failure seen without any hardening: QM cpu load @prio 10; QM memory load @prio 10; QM service crash loop @prio 20; lock shared with QM task (default mutex); detector killed, supervised. That is 0 failures in 5 runs or more each; the 95% upper bound on the failure rate is 43%, so read it as 'not observed', not 'cannot happen'.
* Supervised restart: the detector was back in 5 ms (median of 5 runs); the controller saw a worst gap of 67 ms.
