# Three more attackers

Added after the main report: a memory-bandwidth streamer (`membw`), a swarm of
100-microsecond timers (`timerstorm`) and a kernel-call storm (`kcall`). 5 runs
each, 20 ms deadline, QNX SDP 8.0 in QEMU. Raw runs are in `results/new-*.json`
and `results/new5-*.json`. The first three rows were run against all four profiles
and the last two against `none` and `prio` only.

| Attacker | No hardening | `prio` | `isolate` | `budget` |
|---|---|---|---|---|
| memory bandwidth @ prio 20 | 5/5 failed | 0/5 | 1/5 | 0/5 |
| timer storm @ prio 20 | 0/5 | 0/5 | 0/5 | 0/5 |
| kernel-call storm @ prio 20 | 5/5 failed | 1/5 | 0/5 | 0/5 |
| memory bandwidth @ prio 5 | 1/5 | 0/5 | | |
| kernel-call storm @ prio 5 | 0/5 | 0/5 | | |

What this does and does not show:

* The two attackers that failed the unhardened pipeline at priority 20 never block,
  so they behave as CPU hogs above the pipeline's priority. That is the known
  priority-starvation pattern, not a new one. Raising the pipeline's priority fixes it.
* The test that could separate memory bandwidth from CPU use is the priority-5 run,
  where the pipeline always wins the CPU. There, 1 of 5 unhardened runs failed (worst
  frame 76 ms) and none failed with `prio`. That is too small a difference to call a
  bandwidth effect, and QEMU's memory timing is not hardware's. It is recorded as
  not observed, not as absent.
* A swarm of fast timers did not break the pipeline in any profile in 5 runs. A real
  interrupt storm needs a driver and hardware, so this is only a user-space stand-in.
* The 1 of 5 failures under `prio` for the kernel-call storm is noise-sized and is
  not explained.
