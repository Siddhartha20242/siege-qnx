# Siege report

Each cell is failed runs / total runs for one attack under one hardening profile.

| Scenario | none | prio | isolate | budget |
|---|---|---|---|---|
| baseline (no attacker) | 0/3 | 0/3 | 0/3 | 0/3 |
| cpu hog   @prio 10 | 0/3 | 0/3 | 0/3 | 0/3 |
| cpu hog   @prio 20 | 3/3 | 1/3 | 0/3 | 0/3 |
| flood     @prio 10 | 0/3 | 0/3 | 0/3 | 0/3 |
| flood     @prio 20 | 1/3 | 0/3 | 0/3 | 0/3 |
| workflood @prio 30 | 3/3 | 0/3 | 3/3 | 3/3 |
| mem hog   @prio 10 | 0/3 | 0/3 | 0/3 | 0/3 |
| fd exhaust@prio 10 | 0/3 | 0/3 | 0/3 | 0/3 |
| crash loop@prio 10 | 0/3 | 0/3 | 0/3 | 0/3 |
| crash loop@prio 20 | 0/3 | 0/3 | 0/3 | 0/3 |
| kill detector, no supervisor | 3/3 | 3/3 | 3/3 | 3/3 |
| kill detector, supervised | 0/3 | 0/3 | 0/3 | 0/3 |

## Profiles

* **none**: default round-robin priority 10
* **prio**: pipeline at priority 40
* **isolate**: pipeline on CPU 1, attackers on CPU 0
* **budget**: attackers capped by SCHED_SPORADIC (10 ms / 100 ms)

## Findings

* Baseline: 0/3 runs failed with no attacker; median latency 1.6 ms, worst frame 9.9 ms. Timing is emulated, so read results as relative, not as hardware latencies.
* cpu hog   @prio 20 breaks the unhardened pipeline in 3/3 runs (worst frame 5.0 s, longest silence 5008 ms). Restored by: isolate, budget. Reduced by: prio (1/3 runs still failed).
* workflood @prio 30 breaks the unhardened pipeline in 3/3 runs (worst frame 14.0 ms, longest silence 688 ms). Restored by: prio. Not helped by: isolate, budget.
* kill detector, no supervisor: the pipeline went silent and never recovered in 3/3 runs (the controller gave up after 3 s). Scheduling profiles cannot help; a supervisor can.
* flood     @prio 20 failed 1/3 runs (worst frame 61.0 ms); isolated spikes like this also occur in clean runs under emulation, so treat it as noise unless it repeats.
* Contained by QNX without any hardening (0 failed runs): cpu hog   @prio 10; flood     @prio 10; mem hog   @prio 10; fd exhaust@prio 10; crash loop@prio 10; crash loop@prio 20.
* Supervised restart: the detector was back in 6 ms (median of 3 runs); the controller saw a worst gap of 41 ms.
