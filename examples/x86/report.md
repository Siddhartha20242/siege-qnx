# Siege report

_Measured in QEMU emulation: compare rows with each other, not with hardware latencies._

Without hardening, **4 of 4 attacks** break the pipeline (cpu hog   @prio 20, workflood @prio 30, AI neighbour@prio 20, priority inversion (plain mutex)).
With `prio`: **1 of 4** still break it (priority inversion (plain mutex)).
With `isolate`: **2 of 4** still break it (workflood @prio 30, priority inversion (plain mutex)).
With `budget`: **2 of 4** still break it (workflood @prio 30, priority inversion (plain mutex)).

Each cell is failed runs / total runs for one attack under one hardening profile.

| Scenario | none | prio | isolate | budget |
|---|---|---|---|---|
| baseline (no attacker) | 0/5 | 0/5 | 0/5 | 0/5 |
| cpu hog   @prio 20 | 5/5 | 0/5 | 0/5 | 0/5 |
| workflood @prio 30 | 5/5 | 2/5 | 5/5 | 5/5 |
| AI neighbour@prio 20 | 5/5 | 0/5 | 0/5 | 0/5 |
| priority inversion (plain mutex) | 5/5 | 5/5 | 5/5 | 5/5 |
| kill detector, no supervisor | 5/5 | 5/5 | 5/5 | 5/5 |
| kill detector, supervised | 1/5 | 0/5 | 0/5 | 0/5 |

## Interference evidence by channel

| Channel | Tested | Breaks the unhardened pipeline | Restored by | Not helped by |
|---|---|---|---|---|
| Execution time | 2 scenario(s) | cpu hog   @prio 20, AI neighbour@prio 20 | prio, isolate, budget | - |
| Message exchange | 1 scenario(s) | workflood @prio 30 | - | isolate, budget |
| Shared locks | 1 scenario(s) | priority inversion (plain mutex) | - | prio, isolate, budget |
| Service failure | 2 scenario(s) | kill detector, no supervisor | supervisor | - |

_This is evidence from stress tests of a stand-in pipeline on an emulator. It is not a safety case, a proof of freedom from interference, or a certification claim._

## Profiles

* **none**: default round-robin priority 10
* **prio**: pipeline at priority 40
* **isolate**: pipeline on CPU 1, attackers on CPU 0
* **budget**: attackers capped by SCHED_SPORADIC (10 ms / 100 ms)

## Findings

* Baseline: 0/5 runs failed with no attacker; median latency 4.2 ms, worst frame 8.2 ms. Timing is emulated, so read results as relative, not as hardware latencies.
* cpu hog   @prio 20: the pipeline went silent and never recovered in 5/5 runs (the controller gave up after 3 s). Pattern 5, a dead service with no supervisor (docs/patterns.md): scheduling profiles cannot help; a supervisor can.
* workflood @prio 30: the pipeline went silent and never recovered in 5/5 runs (the controller gave up after 3 s). Pattern 5, a dead service with no supervisor (docs/patterns.md): scheduling profiles cannot help; a supervisor can.
* AI neighbour@prio 20 breaks the unhardened pipeline in 5/5 runs (95% CI 57-100%; worst frame 45.0 ms, longest silence 62 ms). Restored by: prio, isolate, budget. Looks like pattern 3, burst interference (docs/patterns.md): keep inference-style jobs below the pipeline: prio, isolate and budget all work.
* priority inversion (plain mutex): the pipeline went silent and never recovered in 5/5 runs (the controller gave up after 3 s). Pattern 5, a dead service with no supervisor (docs/patterns.md): scheduling profiles cannot help; a supervisor can.
* kill detector, no supervisor: the pipeline went silent and never recovered in 5/5 runs (the controller gave up after 3 s). Pattern 5, a dead service with no supervisor (docs/patterns.md): scheduling profiles cannot help; a supervisor can.
* kill detector, supervised failed 1/5 runs (worst frame 158.6 ms); isolated spikes like this also occur in clean runs under emulation, so treat it as noise unless it repeats.
* Supervised restart: the detector was back in 18 ms (median of 5 runs); the controller saw a worst gap of 176 ms.
