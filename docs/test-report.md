# Siege interference test report

| | |
|---|---|
| Document | Interference test record |
| Date | 2026-11-06 |
| Tool revision | `419592e + uncommitted changes` |
| Test object | Reference camera - detector - controller pipeline on QNX SDP 8.0 |
| Test environment | QEMU emulation (aarch64le, virt machine, 2 CPUs, software emulation) |
| Configuration | deadline 20 ms, tolerance 2.0%, recovery budget 500 ms |
| Result | 68 of 68 test cases matched their expected result |

> **Scope and status.** This document records evidence from stress tests of a stand-in pipeline on an emulator. It is not a safety case, not a proof of freedom from interference, and not a certification claim.

## 1. Pass criteria

1. A run PASSES when at most 2.0% of its frames are late (more than 20 ms from the instant the frame was due) or lost.
2. A run FAILS if the pipeline is silent for longer than 500 ms, or never resumes (the controller gives up after 3 s).
3. When the trained-network detector is used, a run also FAILS if more than 5% of checked detections are wrong (more than 1 pixel from the true position).
4. A test case is OBSERVED as pass when at most 20% of its runs fail, otherwise fail.
5. A test case is a MATCH when its observed result equals its expected result. Expected failures are declared in siege.json (a known weakness of an unhardened configuration is an expected fail, and is reported as a match).

## 2. Requirements and traceability

Derived requirements for this evaluation (not taken from a standard), each traced to the test cases that exercise it.

| Requirement | Statement | Test cases | Matched |
|---|---|---|---|
| REQ-EXE | The pipeline shall meet its frame deadline while another process competes for CPU time. | TC-EXE-01, TC-EXE-02, TC-EXE-03, TC-EXE-04 | 16/16 |
| REQ-MEM | The pipeline shall meet its frame deadline while another process holds and touches memory. | TC-MEM-01 | 4/4 |
| REQ-MSG | The pipeline shall meet its frame deadline while another client abuses a service it shares. | TC-MSG-01, TC-MSG-02, TC-MSG-03 | 12/12 |
| REQ-KOB | The pipeline shall meet its frame deadline while another process exhausts descriptors, channels and connections. | TC-KOB-01 | 4/4 |
| REQ-PRC | The pipeline shall meet its frame deadline while another process crashes and restarts repeatedly. | TC-PRC-01, TC-PRC-02 | 8/8 |
| REQ-LCK | The pipeline shall meet its frame deadline while a low-priority process holds a lock the pipeline needs. | TC-LCK-01, TC-LCK-02, TC-LCK-03 | 12/12 |
| REQ-SVC | The pipeline shall resume delivering frames within the recovery budget after one of its stages is killed. | TC-SVC-01, TC-SVC-02 | 8/8 |

## 3. Test cases

| ID | Stimulus | Configuration | Runs | Failed (95% CI) | Expected | Observed | Result | Worst frame | Longest silence |
|---|---|---|---|---|---|---|---|---|---|
| TC-BAS-01/none | baseline (no attacker) | none | 5 | 0/5 (0-43%) | pass | pass | MATCH | 9.9 ms | 28 ms |
| TC-BAS-01/prio | baseline (no attacker) | prio | 5 | 0/5 (0-43%) | pass | pass | MATCH | 14.4 ms | 31 ms |
| TC-BAS-01/isolate | baseline (no attacker) | isolate | 5 | 0/5 (0-43%) | pass | pass | MATCH | 9.5 ms | 25 ms |
| TC-BAS-01/budget | baseline (no attacker) | budget | 5 | 0/5 (0-43%) | pass | pass | MATCH | 3.5 ms | 22 ms |
| TC-EXE-01/none | cpu hog   @prio 10 | none | 5 | 0/5 (0-43%) | pass | pass | MATCH | 13.1 ms | 31 ms |
| TC-EXE-01/prio | cpu hog   @prio 10 | prio | 5 | 0/5 (0-43%) | pass | pass | MATCH | 4.2 ms | 22 ms |
| TC-EXE-01/isolate | cpu hog   @prio 10 | isolate | 5 | 0/5 (0-43%) | pass | pass | MATCH | 8.7 ms | 27 ms |
| TC-EXE-01/budget | cpu hog   @prio 10 | budget | 5 | 0/5 (0-43%) | pass | pass | MATCH | 14.6 ms | 31 ms |
| TC-EXE-02/none | cpu hog   @prio 20 | none | 15 | 15/15 (80-100%) | fail | fail | MATCH | 5.0 s | 5010 ms |
| TC-EXE-02/prio | cpu hog   @prio 20 | prio | 15 | 0/15 (0-20%) | pass | pass | MATCH | 6.6 ms | 25 ms |
| TC-EXE-02/isolate | cpu hog   @prio 20 | isolate | 15 | 0/15 (0-20%) | pass | pass | MATCH | 14.5 ms | 32 ms |
| TC-EXE-02/budget | cpu hog   @prio 20 | budget | 15 | 1/15 (1-30%) | pass | pass | MATCH | 66.1 ms | 74 ms |
| TC-MSG-01/none | flood     @prio 10 | none | 5 | 0/5 (0-43%) | pass | pass | MATCH | 6.7 ms | 25 ms |
| TC-MSG-01/prio | flood     @prio 10 | prio | 5 | 0/5 (0-43%) | pass | pass | MATCH | 50.6 ms | 68 ms |
| TC-MSG-01/isolate | flood     @prio 10 | isolate | 5 | 0/5 (0-43%) | pass | pass | MATCH | 8.2 ms | 27 ms |
| TC-MSG-01/budget | flood     @prio 10 | budget | 5 | 0/5 (0-43%) | pass | pass | MATCH | 4.6 ms | 22 ms |
| TC-MSG-02/none | flood     @prio 20 | none | 5 | 0/5 (0-43%) | pass | pass | MATCH | 5.6 ms | 24 ms |
| TC-MSG-02/prio | flood     @prio 20 | prio | 5 | 0/5 (0-43%) | pass | pass | MATCH | 15.6 ms | 34 ms |
| TC-MSG-02/isolate | flood     @prio 20 | isolate | 5 | 0/5 (0-43%) | pass | pass | MATCH | 5.9 ms | 24 ms |
| TC-MSG-02/budget | flood     @prio 20 | budget | 5 | 0/5 (0-43%) | pass | pass | MATCH | 3.3 ms | 21 ms |
| TC-MSG-03/none | workflood @prio 30 | none | 15 | 15/15 (80-100%) | fail | fail | MATCH | 16.2 ms | 522 ms |
| TC-MSG-03/prio | workflood @prio 30 | prio | 15 | 1/15 (1-30%) | pass | pass | MATCH | 13.5 ms | 325 ms |
| TC-MSG-03/isolate | workflood @prio 30 | isolate | 15 | 15/15 (80-100%) | fail | fail | MATCH | 5.0 s | 5015 ms |
| TC-MSG-03/budget | workflood @prio 30 | budget | 15 | 15/15 (80-100%) | fail | fail | MATCH | 66.9 ms | 453 ms |
| TC-EXE-03/none | AI neighbour@prio 10 | none | 15 | 0/15 (0-20%) | pass | pass | MATCH | 16.1 ms | 34 ms |
| TC-EXE-03/prio | AI neighbour@prio 10 | prio | 15 | 0/15 (0-20%) | pass | pass | MATCH | 5.0 ms | 24 ms |
| TC-EXE-03/isolate | AI neighbour@prio 10 | isolate | 15 | 0/15 (0-20%) | pass | pass | MATCH | 20.1 ms | 38 ms |
| TC-EXE-03/budget | AI neighbour@prio 10 | budget | 15 | 0/15 (0-20%) | pass | pass | MATCH | 13.8 ms | 32 ms |
| TC-EXE-04/none | AI neighbour@prio 20 | none | 15 | 15/15 (80-100%) | fail | fail | MATCH | 44.4 ms | 61 ms |
| TC-EXE-04/prio | AI neighbour@prio 20 | prio | 15 | 0/15 (0-20%) | pass | pass | MATCH | 11.7 ms | 29 ms |
| TC-EXE-04/isolate | AI neighbour@prio 20 | isolate | 15 | 0/15 (0-20%) | pass | pass | MATCH | 60.0 ms | 77 ms |
| TC-EXE-04/budget | AI neighbour@prio 20 | budget | 15 | 0/15 (0-20%) | pass | pass | MATCH | 57.4 ms | 67 ms |
| TC-LCK-01/none | priority inversion (plain mutex) | none | 5 | 5/5 (57-100%) | fail | fail | MATCH | 64.9 ms | 82 ms |
| TC-LCK-01/prio | priority inversion (plain mutex) | prio | 5 | 5/5 (57-100%) | fail | fail | MATCH | 4.9 ms | 23 ms |
| TC-LCK-01/isolate | priority inversion (plain mutex) | isolate | 5 | 5/5 (57-100%) | fail | fail | MATCH | 17.7 ms | 35 ms |
| TC-LCK-01/budget | priority inversion (plain mutex) | budget | 5 | 5/5 (57-100%) | fail | fail | MATCH | 6.1 ms | 23 ms |
| TC-LCK-02/none | priority inversion (inheriting mutex) | none | 5 | 0/5 (0-43%) | pass | pass | MATCH | 5.6 ms | 23 ms |
| TC-LCK-02/prio | priority inversion (inheriting mutex) | prio | 5 | 0/5 (0-43%) | pass | pass | MATCH | 66.3 ms | 83 ms |
| TC-LCK-02/isolate | priority inversion (inheriting mutex) | isolate | 5 | 0/5 (0-43%) | pass | pass | MATCH | 11.6 ms | 29 ms |
| TC-LCK-02/budget | priority inversion (inheriting mutex) | budget | 5 | 0/5 (0-43%) | pass | pass | MATCH | 32.3 ms | 46 ms |
| TC-LCK-03/none | priority inversion (default mutex) | none | 5 | 0/5 (0-43%) | pass | pass | MATCH | 9.9 ms | 28 ms |
| TC-LCK-03/prio | priority inversion (default mutex) | prio | 5 | 0/5 (0-43%) | pass | pass | MATCH | 9.5 ms | 28 ms |
| TC-LCK-03/isolate | priority inversion (default mutex) | isolate | 5 | 0/5 (0-43%) | pass | pass | MATCH | 20.6 ms | 37 ms |
| TC-LCK-03/budget | priority inversion (default mutex) | budget | 5 | 0/5 (0-43%) | pass | pass | MATCH | 26.8 ms | 43 ms |
| TC-MEM-01/none | mem hog   @prio 10 | none | 5 | 0/5 (0-43%) | pass | pass | MATCH | 8.1 ms | 25 ms |
| TC-MEM-01/prio | mem hog   @prio 10 | prio | 5 | 0/5 (0-43%) | pass | pass | MATCH | 3.9 ms | 22 ms |
| TC-MEM-01/isolate | mem hog   @prio 10 | isolate | 5 | 0/5 (0-43%) | pass | pass | MATCH | 5.7 ms | 24 ms |
| TC-MEM-01/budget | mem hog   @prio 10 | budget | 5 | 0/5 (0-43%) | pass | pass | MATCH | 9.3 ms | 25 ms |
| TC-KOB-01/none | fd exhaust@prio 10 | none | 5 | 0/5 (0-43%) | pass | pass | MATCH | 26.1 ms | 42 ms |
| TC-KOB-01/prio | fd exhaust@prio 10 | prio | 5 | 0/5 (0-43%) | pass | pass | MATCH | 4.9 ms | 22 ms |
| TC-KOB-01/isolate | fd exhaust@prio 10 | isolate | 5 | 0/5 (0-43%) | pass | pass | MATCH | 7.7 ms | 27 ms |
| TC-KOB-01/budget | fd exhaust@prio 10 | budget | 5 | 0/5 (0-43%) | pass | pass | MATCH | 5.5 ms | 23 ms |
| TC-PRC-01/none | crash loop@prio 10 | none | 5 | 0/5 (0-43%) | pass | pass | MATCH | 3.2 ms | 21 ms |
| TC-PRC-01/prio | crash loop@prio 10 | prio | 5 | 0/5 (0-43%) | pass | pass | MATCH | 6.1 ms | 24 ms |
| TC-PRC-01/isolate | crash loop@prio 10 | isolate | 5 | 0/5 (0-43%) | pass | pass | MATCH | 3.4 ms | 22 ms |
| TC-PRC-01/budget | crash loop@prio 10 | budget | 5 | 0/5 (0-43%) | pass | pass | MATCH | 9.9 ms | 29 ms |
| TC-PRC-02/none | crash loop@prio 20 | none | 5 | 0/5 (0-43%) | pass | pass | MATCH | 6.5 ms | 25 ms |
| TC-PRC-02/prio | crash loop@prio 20 | prio | 5 | 0/5 (0-43%) | pass | pass | MATCH | 5.7 ms | 23 ms |
| TC-PRC-02/isolate | crash loop@prio 20 | isolate | 5 | 0/5 (0-43%) | pass | pass | MATCH | 6.9 ms | 25 ms |
| TC-PRC-02/budget | crash loop@prio 20 | budget | 5 | 0/5 (0-43%) | pass | pass | MATCH | 40.5 ms | 58 ms |
| TC-SVC-01/none | kill detector, no supervisor | none | 5 | 5/5 (57-100%) | fail | fail | MATCH | 5.8 ms | 22 ms |
| TC-SVC-01/prio | kill detector, no supervisor | prio | 5 | 5/5 (57-100%) | fail | fail | MATCH | 4.9 ms | 23 ms |
| TC-SVC-01/isolate | kill detector, no supervisor | isolate | 5 | 5/5 (57-100%) | fail | fail | MATCH | 2.7 ms | 21 ms |
| TC-SVC-01/budget | kill detector, no supervisor | budget | 5 | 5/5 (57-100%) | fail | fail | MATCH | 55.4 ms | 72 ms |
| TC-SVC-02/none | kill detector, supervised | none | 15 | 0/15 (0-20%) | pass | pass | MATCH | 24.2 ms | 41 ms |
| TC-SVC-02/prio | kill detector, supervised | prio | 15 | 0/15 (0-20%) | pass | pass | MATCH | 3.3 ms | 40 ms |
| TC-SVC-02/isolate | kill detector, supervised | isolate | 15 | 0/15 (0-20%) | pass | pass | MATCH | 20.5 ms | 41 ms |
| TC-SVC-02/budget | kill detector, supervised | budget | 15 | 0/15 (0-20%) | pass | pass | MATCH | 3.7 ms | 41 ms |

## 4. Environment

* Target: QEMU emulation (aarch64le, virt machine, 2 CPUs, software emulation).
* Operating system: QNX SDP 8.0 (QNX Everywhere, non-commercial licence), toolchain `qcc -Vgcc_ntoaarch64le`.
* Tool revision: `419592e + uncommitted changes`. Raw runs: `docs/results/`.
* Configurations under test: `none` (default round-robin, priority 10), `prio` (pipeline at priority 40), `isolate` (pipeline on CPU 1, attackers on CPU 0), `budget` (attackers capped by SCHED_SPORADIC, 10 ms per 100 ms).

## 5. Limits of this evidence

* All timing is from QEMU emulation. It is not hardware timing, and no result here has been reproduced on a real target.
* The pipeline and its input are synthetic. Every run sees the same frames, which makes runs comparable but does not represent a real sensor.
* The number of runs per case is small (5 to 15). A case with no observed failure is consistent with a failure rate up to the upper confidence bound (43% at 5 runs).
* Only the interference mechanisms listed above were tried. Passing every case does not show freedom from interference in general.
* Adaptive partitioning is not part of the free SDK and was not evaluated; sporadic scheduling budgets were used for CPU limits.

## 6. Review

| Role | Name | Date | Signature |
|---|---|---|---|
| Author | | | |
| Reviewer | | | |
