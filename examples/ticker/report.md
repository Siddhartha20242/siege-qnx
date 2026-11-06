# Siege report

Each cell is failed runs / total runs for one attack under one hardening profile.

| Scenario | none | prio |
|---|---|---|
| baseline (no attacker) | 0/3 | 0/3 |
| cpu hog   @prio 10 | 3/3 | 0/3 |
| cpu hog   @prio 20 | 3/3 | 0/3 |
| crash loop@prio 20 | 3/3 | 0/3 |

## Profiles

* **none**: default round-robin priority 10
* **prio**: pipeline at priority 40

## Findings

* Baseline: 0/3 runs failed with no attacker; median latency 1.4 ms, worst frame 11.0 ms. Timing is emulated, so read results as relative, not as hardware latencies.
* cpu hog   @prio 10 breaks the unhardened pipeline in 3/3 runs (worst frame 11.0 ms). Restored by: prio.
* cpu hog   @prio 20 breaks the unhardened pipeline in 3/3 runs (worst frame 5.0 s). Restored by: prio.
* crash loop@prio 20 breaks the unhardened pipeline in 3/3 runs (worst frame 11.4 ms). Restored by: prio.
