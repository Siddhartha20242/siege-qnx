# Failure search

60 random combinations of one to 3 attackers at priority 5,10 (the pipeline runs at 10), profile `none`, seed 20261107, 4 s runs, 20 ms deadline. A combination counts as failing only if the pipeline failed in all 2 runs. 61 distinct configurations were run in 7 minutes. QEMU emulation.

| Minimal failing case | Priority | Kind |
|---|---|---|
| `membw` | 10 | known pattern (one attacker breaks it alone) |
| `workflood` | 10 | known pattern (one attacker breaks it alone) |


Limits: random search, so a case not listed was not found, not shown impossible. Emulator timing. Raw runs: `results/search.json`.
