# How weak can the attack be?

Every attacker elsewhere in this repository is a point somebody chose. This page
asks a different question: how little does an attacker have to do to break the
pipeline? The attacker is `workflood` (each request costs the shared detector 150
passes of work, two threads), run at several priorities and several request
rates, with no hardening profile, 5 s runs, 20 ms deadline, 3 runs per cell, in
QEMU. The pipeline itself runs at priority 10.

Failed runs out of 3 (`./siege frontier measure`, 19.5 minutes,
raw data in `docs/results/frontier-grid.json`):

| req/s per thread \ attacker priority | 5 | 10 | 15 | 20 | 30 | 50 |
|---|---|---|---|---|---|---|
| 5 | 0/3 | 0/3 | 0/3 | 0/3 | 1/3 | 0/3 |
| 10 | 0/3 | 0/3 | 1/3 | 0/3 | 0/3 | 0/3 |
| 20 | 0/3 | 1/3 | 2/3 | 3/3 | 2/3 | 2/3 |
| 35 | 1/3 | 1/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| 60 | 0/3 | 2/3 | 3/3 | 2/3 | 3/3 | 3/3 |
| 100 | 0/3 | 0/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| 170 | 0/3 | 2/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| 300 | 0/3 | 2/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| max | 0/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |

## What the map says

* **Priority decides first.** At priority 5, below the pipeline, 1 of 27 runs failed at any rate, even flat out.
* **Above the pipeline, a modest rate is enough.** At priorities 15 to 50, 35
  requests per second per thread (70 per second from two threads) failed 3 of 3 in every
  column; 20 per second failed 2 or 3 of 3 at those priorities; 10 per second failed at most 1 of 3. The edge is soft, not a clean line.
* **At the pipeline's own priority (10) results are mixed** (0 to 3 of 3 failing, rising with rate; flat out 3 of 3). That matches the unstable equal-priority cell in [`more-attackers.md`](more-attackers.md); with 3 runs per cell it is not resolved here.
* This is the same mechanism as the 0.4% CPU finding: the cost is the work the
  detector does at the attacker's priority, so what matters is request rate times
  cost, not the attacker's own CPU.

## Letting a small model choose the cells

Running all 54 cells took 19.5 minutes. `./siege frontier` can instead
learn the boundary: a logistic regression on priority and log request rate
(about 30 lines of numpy, trained from scratch) is fitted to the cells run so far,
and the next cell is the one it is least sure about.

Offline replay, using the measured grid as the answer key, 300 random seeds,
accuracy = share of all 54 cells classified correctly (5th to 95th percentile in brackets):

| Cells run | Random choice | Learner's choice |
|---|---|---|
| 6 of 54 | 77% (59%-87%) | 79% (59%-87%) |
| 8 of 54 | 80% (65%-89%) | 83% (72%-89%) |
| 10 of 54 | 82% (69%-89%) | 85% (80%-91%) |
| 14 of 54 | 85% (76%-91%) | 88% (83%-93%) |
| 18 of 54 | 86% (80%-91%) | 90% (85%-94%) |
| 24 of 54 | 87% (81%-91%) | 92% (89%-96%) |

The learner is better at every budget, by about 3 to 5 points on average, and its
poor runs are much less poor (24 cells: worst 5% reach 89% against 81%). That is
a modest gain, not a breakthrough. It is a small, honest speed-up on one two-dial
attack, and the replay only simulates choices from a table that was itself
measured with noise.

Live check: `./siege frontier active --budget 14` ran 14 cells on QNX and
predicted the other 40. Scored against the full grid it got 46 of 54 cells right (85%),
in line with the replay's 88% mean at 14 cells (`docs/results/frontier-active.txt`).

## What this does not show

* One attacker, two dials, one profile. Other attackers and the hardening
  profiles were not mapped.
* 3 runs per cell and a majority rule; several cells are 1/3 or 2/3, so their
  label is uncertain. The learner is scored against those noisy labels.
* The live check is one seed, not a benchmark.
* QEMU timing, not hardware.

## What the grid says about the mechanism

A QNX engineer reviewing this project objected that the priority boost of the server (it runs at its client's priority
while serving) was never separated from the queue order and serial service of a single-threaded server. The grid helps
a little, with the limit that each cell is only 3 runs:

| Flood rate per thread | Priority 5 (below the pipeline) | Priority 10 (equal, no boost possible) |
|---|---|---|
| 60 to maximum (5 rates) | 0 of 15 runs failed | 9 of 15 runs failed |

An equal-priority client did hurt the pipeline at high enough rates, and a lower-priority client did not. That is consistent with serial
service of expensive requests, but it cannot separate the two causes: at priority 5 the detector is also *lowered* while it serves the
flood, and at equal priority the queue is first-in first-out, so this shows serial-service load, not priority-ordered queuing. The real
test is the control experiment in [`mechanism-control.md`](mechanism-control.md). A multi-threaded detector or per-client limits were not built.
