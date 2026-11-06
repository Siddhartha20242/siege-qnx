# Siege report

_Measured in QEMU emulation: compare rows with each other, not with hardware latencies._

Without hardening, **4 of 14 attacks** break the pipeline (cpu hog   @prio 20, workflood @prio 30, AI neighbour@prio 20, priority inversion (plain mutex)).
With `prio`: **1 of 14** still break it (priority inversion (plain mutex)).
With `isolate`: **2 of 14** still break it (workflood @prio 30, priority inversion (plain mutex)).
With `budget`: **2 of 14** still break it (workflood @prio 30, priority inversion (plain mutex)).

Each cell is failed runs / total runs for one attack under one hardening profile.

| Scenario | none | prio | isolate | budget |
|---|---|---|---|---|
| baseline (no attacker) | 0/5 | 0/5 | 0/5 | 0/5 |
| cpu hog   @prio 10 | 0/5 | 0/5 | 0/5 | 0/5 |
| cpu hog   @prio 20 | 15/15 | 0/15 | 0/15 | 1/15 |
| flood     @prio 10 | 0/5 | 0/5 | 0/5 | 0/5 |
| flood     @prio 20 | 0/5 | 0/5 | 0/5 | 0/5 |
| workflood @prio 30 | 15/15 | 1/15 | 15/15 | 15/15 |
| AI neighbour@prio 10 | 0/15 | 0/15 | 0/15 | 0/15 |
| AI neighbour@prio 20 | 15/15 | 0/15 | 0/15 | 0/15 |
| priority inversion (plain mutex) | 5/5 | 5/5 | 5/5 | 5/5 |
| priority inversion (inheriting mutex) | 0/5 | 0/5 | 0/5 | 0/5 |
| priority inversion (default mutex) | 0/5 | 0/5 | 0/5 | 0/5 |
| mem hog   @prio 10 | 0/5 | 0/5 | 0/5 | 0/5 |
| fd exhaust@prio 10 | 0/5 | 0/5 | 0/5 | 0/5 |
| crash loop@prio 10 | 0/5 | 0/5 | 0/5 | 0/5 |
| crash loop@prio 20 | 0/5 | 0/5 | 0/5 | 0/5 |
| kill detector, no supervisor | 5/5 | 5/5 | 5/5 | 5/5 |
| kill detector, supervised | 0/15 | 0/15 | 0/15 | 0/15 |

## Interference evidence by channel

| Channel | Tested | Breaks the unhardened pipeline | Restored by | Not helped by |
|---|---|---|---|---|
| Execution time | 4 scenario(s) | cpu hog   @prio 20, AI neighbour@prio 20 | prio, isolate, budget (1/30 runs still failed) | - |
| Memory | 1 scenario(s) | nothing observed | - | - |
| Message exchange | 3 scenario(s) | workflood @prio 30 | prio (1/15 runs still failed) | isolate, budget |
| Kernel objects | 1 scenario(s) | nothing observed | - | - |
| Process failure | 2 scenario(s) | nothing observed | - | - |
| Shared locks | 3 scenario(s) | priority inversion (plain mutex) | a priority-inheriting mutex (the default mutex is also safe) | prio, isolate, budget |
| Service failure | 2 scenario(s) | kill detector, no supervisor | supervisor | - |

_This is evidence from stress tests of a stand-in pipeline on an emulator. It is not a safety case, a proof of freedom from interference, or a certification claim._

## Profiles

* **none**: default round-robin priority 10
* **prio**: pipeline at priority 40
* **isolate**: pipeline on CPU 1, attackers on CPU 0
* **budget**: attackers capped by SCHED_SPORADIC (10 ms / 100 ms)

## Findings

* Baseline: 0/5 runs failed with no attacker; median latency 1.6 ms, worst frame 9.9 ms. Timing is emulated, so read results as relative, not as hardware latencies.
* cpu hog   @prio 20 breaks the unhardened pipeline in 15/15 runs (95% CI 80-100%; worst frame 5.0 s, longest silence 5010 ms). Restored by: prio, isolate, budget (1/15 runs still failed). Looks like pattern 1, priority starvation (docs/patterns.md): put the pipeline above its neighbours (prio), give it a CPU of its own (isolate), or cap the neighbour (budget).
* workflood @prio 30 breaks the unhardened pipeline in 15/15 runs (95% CI 80-100%; worst frame 16.2 ms, longest silence 522 ms). Restored by: prio (1/15 runs still failed). Not helped by: isolate, budget. Looks like pattern 2, queue-priority starvation (docs/patterns.md): raise the pipeline's priority above every client of the shared service; CPU isolation and CPU budgets do not help.
* AI neighbour@prio 20 breaks the unhardened pipeline in 15/15 runs (95% CI 80-100%; worst frame 44.4 ms, longest silence 61 ms). Restored by: prio, isolate, budget. Looks like pattern 3, burst interference (docs/patterns.md): keep inference-style jobs below the pipeline: prio, isolate and budget all work.
* priority inversion (plain mutex): the pipeline went silent and never recovered in 5/5 runs (the controller gave up after 3 s). Pattern 5, a dead service with no supervisor (docs/patterns.md): scheduling profiles cannot help; a supervisor can.
* kill detector, no supervisor: the pipeline went silent and never recovered in 5/5 runs (the controller gave up after 3 s). Pattern 5, a dead service with no supervisor (docs/patterns.md): scheduling profiles cannot help; a supervisor can.
* No failure seen without any hardening: cpu hog   @prio 10; flood     @prio 10; flood     @prio 20; AI neighbour@prio 10; priority inversion (inheriting mutex); priority inversion (default mutex); mem hog   @prio 10; fd exhaust@prio 10; crash loop@prio 10; crash loop@prio 20. That is 0 failures in 5 runs or more each; the 95% upper bound on the failure rate is 43%, so read it as 'not observed', not 'cannot happen'.
* Supervised restart: the detector was back in 5 ms (median of 15 runs); the controller saw a worst gap of 41 ms.
