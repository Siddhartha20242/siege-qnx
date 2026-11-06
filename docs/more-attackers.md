# Three more attackers

A memory-bandwidth streamer (`membw`), a swarm of 100-microsecond timers
(`timerstorm`) and a kernel-call storm (`kcall`). 20 ms deadline, QNX SDP 8.0 in
QEMU. Raw runs: `results/new-*.json` (5 runs each) and `results/deep2-*.json` (15
runs each, the table below). `timerstorm` was run 5 times per profile only.

Failed runs out of 15 (95% Wilson interval for the failure rate in brackets):

| Attacker | No hardening | `prio` | `isolate` | `budget` |
|---|---|---|---|---|
| memory bandwidth @ prio 20 | 15/15 (78-100%) | 0/15 (0-20%) | 0/15 (0-20%) | 1/15 (1-30%) |
| kernel-call storm @ prio 20 | 15/15 (78-100%) | 0/15 (0-20%) | 0/15 (0-20%) | 0/15 (0-20%) |
| memory bandwidth @ prio 5 | 0/15 (0-20%) | 0/15 (0-20%) | 0/15 (0-20%) | 0/15 (0-20%) |
| kernel-call storm @ prio 5 | 0/15 (0-20%) | 1/15 (1-30%) | 0/15 (0-20%) | 0/15 (0-20%) |
| timer storm @ prio 20 (5 runs) | 0/5 | 0/5 | 0/5 | 0/5 |

What this shows and does not show:

* The two attackers that fail the unhardened pipeline at priority 20 never block, so
  they behave as CPU hogs above the pipeline's priority. That is the known
  priority-starvation pattern, not a new one, and raising the pipeline's priority,
  giving it its own CPU, or capping the attacker's CPU all fix it.
* At priority 5, where the pipeline always wins the CPU, neither attacker broke it in
  15 runs. The 1 of 5 failure seen earlier for memory bandwidth did not repeat, so it
  was noise. No memory-bandwidth effect was observed. QEMU's memory timing is not
  hardware's, so this says nothing about a real board.
* The two single failures in the table (one `budget` run, one `prio` run with a worst frame
  of 125 ms) are within what the emulator does on its own; the baseline also has
  occasional frames over 30 ms. They are not explained.
* A swarm of fast timers did not break the pipeline in any profile in 5 runs. A real
  interrupt storm needs a driver and hardware; this is only a user-space stand-in.
