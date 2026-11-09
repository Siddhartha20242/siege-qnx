# Siege report

_Measured in QEMU emulation: compare rows with each other, not with hardware latencies._

Without hardening, **9 of 23 attacks** break the pipeline (cpu hog   @prio 10, cpu hog   @prio 20, workflood @prio 30, AI neighbour@prio 20, priority inversion (plain mutex), memory bandwidth @prio 20, kernel-call storm @prio 20, memory bandwidth @prio 10, name squat, race after restart).
With `prio`: **2 of 23** still break it (priority inversion (plain mutex), name squat, race after restart).
With `isolate`: **3 of 23** still break it (workflood @prio 30, priority inversion (plain mutex), name squat, race after restart).
With `budget`: **3 of 23** still break it (workflood @prio 30, priority inversion (plain mutex), name squat, race after restart).

Each cell is failed runs / total runs for one attack under one hardening profile.

| Scenario | none | prio | isolate | budget |
|---|---|---|---|---|
| baseline (no attacker) | 0/15 | 0/15 | 0/15 | 0/15 |
| cpu hog   @prio 10 | 9/15 | 0/15 | 0/15 | 1/15 |
| cpu hog   @prio 20 | 15/15 | 0/15 | 0/15 | 1/15 |
| flood     @prio 10 | 0/15 | 0/15 | 0/15 | 0/15 |
| flood     @prio 20 | 1/15 | 0/15 | 0/15 | 0/15 |
| workflood @prio 30 | 15/15 | 1/15 | 15/15 | 15/15 |
| AI neighbour@prio 10 | 0/15 | 0/15 | 0/15 | 0/15 |
| AI neighbour@prio 20 | 15/15 | 0/15 | 0/15 | 0/15 |
| priority inversion (plain mutex) | 15/15 | 15/15 | 15/15 | 15/15 |
| priority inversion (inheriting mutex) | 1/15 | 0/15 | 0/15 | 0/15 |
| priority inversion (default mutex) | 0/15 | 0/15 | 0/15 | 0/15 |
| mem hog   @prio 10 | 1/15 | 0/15 | 0/15 | 0/15 |
| fd exhaust@prio 10 | 0/15 | 0/15 | 0/15 | 0/15 |
| crash loop@prio 10 | 0/15 | 0/15 | 0/15 | 0/15 |
| crash loop@prio 20 | 0/15 | 0/15 | 0/15 | 0/15 |
| kill detector, no supervisor | 15/15 | 15/15 | 15/15 | 15/15 |
| kill detector, supervised | 0/15 | 0/15 | 0/15 | 0/15 |
| memory bandwidth @prio 20 | 15/15 | 0/15 | 0/15 | 0/15 |
| timer storm @prio 20 | 0/15 | 0/15 | 0/15 | 0/15 |
| kernel-call storm @prio 20 | 15/15 | 0/15 | 0/15 | 2/15 |
| memory bandwidth @prio 5 | 0/15 | 0/15 | 0/15 | 0/15 |
| kernel-call storm @prio 5 | 0/15 | 0/15 | 0/15 | 0/15 |
| memory bandwidth @prio 10 | 15/15 | 0/15 | 0/15 | 0/15 |
| name squat, detector alive | 0/10 | 0/10 | 0/10 | 0/10 |
| name squat, race after restart | 10/10 | 8/10 | 10/10 | 8/10 |
| name squat, race after restart (owner check) | 0/10 | 0/10 | 0/10 | 0/10 |

## Interference evidence by channel

| Channel | Tested | Breaks the unhardened pipeline | Restored by | Not helped by |
|---|---|---|---|---|
| Execution time | 4 scenario(s) | cpu hog   @prio 10, cpu hog   @prio 20, AI neighbour@prio 20 | prio, isolate, budget (2/45 runs still failed) | - |
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
* **budget**: attackers demoted to priority 2 by SCHED_SPORADIC after 10 ms of CPU per 100 ms

## Findings

* Baseline: 0/15 runs failed with no attacker; median latency 1.6 ms, worst frame 5.9 ms. Timing is emulated, so read results as relative, not as hardware latencies.
* cpu hog   @prio 10 breaks the unhardened pipeline in 9/15 runs (95% CI 36-80%; worst frame 33.2 ms, longest silence 48 ms). Restored by: prio, isolate, budget (1/15 runs still failed). Looks like pattern 4, same-priority timeslice jitter (docs/patterns.md): give the pipeline a higher priority than its neighbours, or relax a deadline that has no slack.
* cpu hog   @prio 20: the pipeline went silent and never recovered in 15/15 runs (the controller gave up after 3 s). Pattern 5, a dead service with no supervisor (docs/patterns.md): scheduling profiles cannot help; a supervisor can.
* workflood @prio 30: the pipeline went silent and never recovered in 15/15 runs (the controller gave up after 3 s). Pattern 5, a dead service with no supervisor (docs/patterns.md): scheduling profiles cannot help; a supervisor can.
* AI neighbour@prio 20 breaks the unhardened pipeline in 15/15 runs (95% CI 80-100%; worst frame 90.8 ms, longest silence 107 ms). Restored by: prio, isolate, budget. Looks like pattern 3, burst interference (docs/patterns.md): keep inference-style jobs below the pipeline: prio, isolate and budget all work.
* priority inversion (plain mutex): the pipeline went silent and never recovered in 15/15 runs (the controller gave up after 3 s). Pattern 5, a dead service with no supervisor (docs/patterns.md): scheduling profiles cannot help; a supervisor can.
* kill detector, no supervisor: the pipeline went silent and never recovered in 15/15 runs (the controller gave up after 3 s). Pattern 5, a dead service with no supervisor (docs/patterns.md): scheduling profiles cannot help; a supervisor can.
* memory bandwidth @prio 20: the pipeline went silent and never recovered in 15/15 runs (the controller gave up after 3 s). Pattern 5, a dead service with no supervisor (docs/patterns.md): scheduling profiles cannot help; a supervisor can.
* kernel-call storm @prio 20: the pipeline went silent and never recovered in 15/15 runs (the controller gave up after 3 s). Pattern 5, a dead service with no supervisor (docs/patterns.md): scheduling profiles cannot help; a supervisor can.
* memory bandwidth @prio 10 breaks the unhardened pipeline in 15/15 runs (95% CI 80-100%; worst frame 107.1 ms, longest silence 99 ms). Restored by: prio, isolate, budget.
* name squat, race after restart: the pipeline went silent and never recovered in 10/10 runs (the controller gave up after 3 s). Pattern 5, a dead service with no supervisor (docs/patterns.md): scheduling profiles cannot help; a supervisor can.
* flood     @prio 20 failed 1/15 runs (worst frame 60.6 ms); isolated spikes like this also occur in clean runs under emulation, so treat it as noise unless it repeats.
* priority inversion (inheriting mutex) failed 1/15 runs (worst frame 47.6 ms); isolated spikes like this also occur in clean runs under emulation, so treat it as noise unless it repeats.
* mem hog   @prio 10 failed 1/15 runs (worst frame 72.5 ms); isolated spikes like this also occur in clean runs under emulation, so treat it as noise unless it repeats.
* No failure seen without any hardening: flood     @prio 10; AI neighbour@prio 10; priority inversion (default mutex); fd exhaust@prio 10; crash loop@prio 10; crash loop@prio 20; timer storm @prio 20; memory bandwidth @prio 5; kernel-call storm @prio 5; name squat, detector alive; name squat, race after restart (owner check). That is 0 failures in 10 runs or more each; the 95% upper bound on the failure rate is 28%, so read it as 'not observed', not 'cannot happen'.
* Supervised restart: the detector was back in 3 ms (median of 15 runs); the controller saw a worst gap of 56 ms.
