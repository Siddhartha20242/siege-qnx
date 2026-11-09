# Three more attackers

A memory-bandwidth streamer (`membw`), a swarm of 100-microsecond timers
(`timerstorm`) and a kernel-call storm (`kcall`). 20 ms deadline, QNX SDP 8.0 in
QEMU. Raw runs: `results/new-*.json` (5 runs each) and `results/deep2-*.json` (15
runs each, the table below). `timerstorm` was run 5 times per profile only.

Failed runs out of 15 (95% Wilson interval for the failure rate in brackets):

| Attacker | No hardening | `prio` | `isolate` | `budget` |
|---|---|---|---|---|
| memory bandwidth @ prio 20 | 15/15 (80-100%) | 0/15 (0-20%) | 0/15 (0-20%) | 1/15 (1-30%) |
| kernel-call storm @ prio 20 | 15/15 (80-100%) | 0/15 (0-20%) | 0/15 (0-20%) | 0/15 (0-20%) |
| memory bandwidth @ prio 5 | 0/15 (0-20%) | 0/15 (0-20%) | 0/15 (0-20%) | 0/15 (0-20%) |
| kernel-call storm @ prio 5 | 0/15 (0-20%) | 1/15 (1-30%) | 0/15 (0-20%) | 0/15 (0-20%) |
| timer storm @ prio 20 (5 runs) | 0/5 | 0/5 | 0/5 | 0/5 |

What this shows and does not show:

* The two attackers that fail the unhardened pipeline at priority 20 never block, so
  they behave as CPU hogs above the pipeline's priority. That is the known
  priority-starvation pattern, not a new one, and raising the pipeline's priority,
  giving it its own CPU, or demoting the attacker after a CPU budget all fix it.
* At priority 5, where the pipeline always wins the CPU, neither attacker broke it in
  15 runs. The 1 of 5 failure seen earlier for memory bandwidth did not repeat, so it
  was noise. No memory-bandwidth effect was observed. QEMU's memory timing is not
  hardware's, so this says nothing about a real board.
* The two single failures in the table (one `budget` run, one `prio` run with a worst frame
  of 125 ms) are within what the emulator does on its own; the baseline also has
  occasional frames over 30 ms. They are not explained.
* A swarm of fast timers did not break the pipeline in any profile in 5 runs. A real
  interrupt storm needs a driver and hardware; this is only a user-space stand-in.

## Equal priority (found by `./siege search`, then checked with 15 runs)

`./siege search` ([`search.md`](search.md)) tried 60 random combinations of one to three
attackers at priority 5 or 10 against the pipeline (priority 10). Nothing at priority 5
broke it. At priority 10, two single attackers did, and no combination failed where its
members passed alone, so it found no interaction failure.

| At the same priority (10) | No hardening | `prio` | `isolate` | `budget` |
|---|---|---|---|---|
| memory bandwidth | 10/15 | 0/15 | 0/15 | 1/15 |
| CPU hog | 8/15 (11/15 in a repeat) | 0/15 | 0/15 | 0/15 |
| baseline, no attacker (repeat run) | 0/15 | | | |

The CPU hog result contradicts an earlier 5-run check (0/5) that this repository's report
and landscape used. The baseline is clean, so the pipeline is not simply flaky now. The
likely cause is that equal-priority sharing is timeslice-based and its effect on a 20 ms
deadline depends on how fast the emulated CPU runs, which changes with the load on the
host Mac. I have not tested that explanation. Higher pipeline priority removed it in
every run. The earlier documents have been updated to say so.

## The full 15-run matrix, and a long-boot artefact

Every scenario was then run 15 times under every profile (`results/full-*.json`, 23 scenarios
x 4 profiles). In that run, the last scenarios of the `prio` profile (memory bandwidth at
priority 5 and 10, kernel-call storm at priority 5) lost 10 of 45 runs to "no result", and
the runs that did return showed failures (3 of 9, 1 of 12, 2 of 14) that make no sense: the
attacker was at priority 5 and the pipeline at 40. One `isolate` run of `workflood` was also
lost. The same scenarios run again in fresh boots (`results/rerun-*.json`) lost no runs and
failed none (0 of 15 each), and the `isolate` workflood result reproduced at 15 of 15.

The reports use the re-runs for those cells and keep the original files. The likely cause is
that the guest degrades over one long boot of about 90 minutes, but I did not test that.
Practical consequence: for long matrices, split them into several boots. The report tools
now prefer the file with more valid runs, and the later file on a tie.
