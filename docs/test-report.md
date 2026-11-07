# Siege interference test report

| | |
|---|---|
| Document | Interference test record |
| Date | 2026-11-07 |
| Tool revision | `e175c26 + uncommitted changes` |
| Test object | Reference camera - detector - controller pipeline on QNX SDP 8.0 |
| Test environment | QEMU emulation (aarch64le, virt machine, 2 CPUs, software emulation) |
| Configuration | deadline 20 ms, tolerance 2.0%, recovery budget 500 ms |
| Result | 104 of 104 test cases matched their expected result |

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
| TC-BAS-01/none | baseline (no attacker) | none | 15 | 0/15 (0-20%) | pass | pass | MATCH | 5.9 ms | 25 ms |
| TC-BAS-01/prio | baseline (no attacker) | prio | 15 | 0/15 (0-20%) | pass | pass | MATCH | 71.2 ms | 87 ms |
| TC-BAS-01/isolate | baseline (no attacker) | isolate | 15 | 0/15 (0-20%) | pass | pass | MATCH | 6.6 ms | 25 ms |
| TC-BAS-01/budget | baseline (no attacker) | budget | 15 | 0/15 (0-20%) | pass | pass | MATCH | 33.3 ms | 51 ms |
| TC-EXE-01/none | cpu hog   @prio 10 | none | 15 | 9/15 (36-80%) | fail | fail | MATCH | 33.2 ms | 48 ms |
| TC-EXE-01/prio | cpu hog   @prio 10 | prio | 15 | 0/15 (0-20%) | pass | pass | MATCH | 71.9 ms | 78 ms |
| TC-EXE-01/isolate | cpu hog   @prio 10 | isolate | 15 | 0/15 (0-20%) | pass | pass | MATCH | 11.4 ms | 28 ms |
| TC-EXE-01/budget | cpu hog   @prio 10 | budget | 15 | 1/15 (1-30%) | pass | pass | MATCH | 125.1 ms | 143 ms |
| TC-EXE-02/none | cpu hog   @prio 20 | none | 15 | 15/15 (80-100%) | fail | fail | MATCH | 5.0 s | 5000 ms |
| TC-EXE-02/prio | cpu hog   @prio 20 | prio | 15 | 0/15 (0-20%) | pass | pass | MATCH | 49.5 ms | 47 ms |
| TC-EXE-02/isolate | cpu hog   @prio 20 | isolate | 15 | 0/15 (0-20%) | pass | pass | MATCH | 42.3 ms | 53 ms |
| TC-EXE-02/budget | cpu hog   @prio 20 | budget | 15 | 1/15 (1-30%) | pass | pass | MATCH | 45.8 ms | 63 ms |
| TC-MSG-01/none | flood     @prio 10 | none | 15 | 0/15 (0-20%) | pass | pass | MATCH | 11.1 ms | 29 ms |
| TC-MSG-01/prio | flood     @prio 10 | prio | 15 | 0/15 (0-20%) | pass | pass | MATCH | 7.4 ms | 26 ms |
| TC-MSG-01/isolate | flood     @prio 10 | isolate | 15 | 0/15 (0-20%) | pass | pass | MATCH | 10.7 ms | 28 ms |
| TC-MSG-01/budget | flood     @prio 10 | budget | 15 | 0/15 (0-20%) | pass | pass | MATCH | 9.8 ms | 28 ms |
| TC-MSG-02/none | flood     @prio 20 | none | 15 | 1/15 (1-30%) | pass | pass | MATCH | 60.6 ms | 69 ms |
| TC-MSG-02/prio | flood     @prio 20 | prio | 15 | 0/15 (0-20%) | pass | pass | MATCH | 13.8 ms | 52 ms |
| TC-MSG-02/isolate | flood     @prio 20 | isolate | 15 | 0/15 (0-20%) | pass | pass | MATCH | 10.2 ms | 28 ms |
| TC-MSG-02/budget | flood     @prio 20 | budget | 15 | 0/15 (0-20%) | pass | pass | MATCH | 6.8 ms | 23 ms |
| TC-MSG-03/none | workflood @prio 30 | none | 15 | 15/15 (80-100%) | fail | fail | MATCH | 80.9 ms | 1398 ms |
| TC-MSG-03/prio | workflood @prio 30 | prio | 15 | 1/15 (1-30%) | pass | pass | MATCH | 68.5 ms | 103 ms |
| TC-MSG-03/isolate | workflood @prio 30 | isolate | 15 | 15/15 (80-100%) | fail | fail | MATCH | 1.6 s | 1658 ms |
| TC-MSG-03/budget | workflood @prio 30 | budget | 15 | 15/15 (80-100%) | fail | fail | MATCH | 15.1 ms | 63 ms |
| TC-EXE-03/none | AI neighbour@prio 10 | none | 15 | 0/15 (0-20%) | pass | pass | MATCH | 26.9 ms | 45 ms |
| TC-EXE-03/prio | AI neighbour@prio 10 | prio | 15 | 0/15 (0-20%) | pass | pass | MATCH | 34.1 ms | 52 ms |
| TC-EXE-03/isolate | AI neighbour@prio 10 | isolate | 15 | 0/15 (0-20%) | pass | pass | MATCH | 9.8 ms | 26 ms |
| TC-EXE-03/budget | AI neighbour@prio 10 | budget | 15 | 0/15 (0-20%) | pass | pass | MATCH | 29.4 ms | 46 ms |
| TC-EXE-04/none | AI neighbour@prio 20 | none | 15 | 15/15 (80-100%) | fail | fail | MATCH | 90.8 ms | 107 ms |
| TC-EXE-04/prio | AI neighbour@prio 20 | prio | 15 | 0/15 (0-20%) | pass | pass | MATCH | 30.3 ms | 35 ms |
| TC-EXE-04/isolate | AI neighbour@prio 20 | isolate | 15 | 0/15 (0-20%) | pass | pass | MATCH | 10.6 ms | 29 ms |
| TC-EXE-04/budget | AI neighbour@prio 20 | budget | 15 | 0/15 (0-20%) | pass | pass | MATCH | 19.7 ms | 37 ms |
| TC-LCK-01/none | priority inversion (plain mutex) | none | 15 | 15/15 (80-100%) | fail | fail | MATCH | 6.0 ms | 23 ms |
| TC-LCK-01/prio | priority inversion (plain mutex) | prio | 15 | 15/15 (80-100%) | fail | fail | MATCH | 15.1 ms | 32 ms |
| TC-LCK-01/isolate | priority inversion (plain mutex) | isolate | 15 | 15/15 (80-100%) | fail | fail | MATCH | 10.4 ms | 28 ms |
| TC-LCK-01/budget | priority inversion (plain mutex) | budget | 15 | 15/15 (80-100%) | fail | fail | MATCH | 4.9 ms | 22 ms |
| TC-LCK-02/none | priority inversion (inheriting mutex) | none | 15 | 1/15 (1-30%) | pass | pass | MATCH | 47.6 ms | 64 ms |
| TC-LCK-02/prio | priority inversion (inheriting mutex) | prio | 15 | 0/15 (0-20%) | pass | pass | MATCH | 11.9 ms | 30 ms |
| TC-LCK-02/isolate | priority inversion (inheriting mutex) | isolate | 15 | 0/15 (0-20%) | pass | pass | MATCH | 10.1 ms | 26 ms |
| TC-LCK-02/budget | priority inversion (inheriting mutex) | budget | 15 | 0/15 (0-20%) | pass | pass | MATCH | 6.2 ms | 25 ms |
| TC-LCK-03/none | priority inversion (default mutex) | none | 15 | 0/15 (0-20%) | pass | pass | MATCH | 9.0 ms | 25 ms |
| TC-LCK-03/prio | priority inversion (default mutex) | prio | 15 | 0/15 (0-20%) | pass | pass | MATCH | 7.5 ms | 26 ms |
| TC-LCK-03/isolate | priority inversion (default mutex) | isolate | 15 | 0/15 (0-20%) | pass | pass | MATCH | 9.6 ms | 27 ms |
| TC-LCK-03/budget | priority inversion (default mutex) | budget | 15 | 0/15 (0-20%) | pass | pass | MATCH | 6.7 ms | 24 ms |
| TC-MEM-01/none | mem hog   @prio 10 | none | 15 | 1/15 (1-30%) | pass | pass | MATCH | 72.5 ms | 87 ms |
| TC-MEM-01/prio | mem hog   @prio 10 | prio | 15 | 0/15 (0-20%) | pass | pass | MATCH | 103.7 ms | 119 ms |
| TC-MEM-01/isolate | mem hog   @prio 10 | isolate | 15 | 0/15 (0-20%) | pass | pass | MATCH | 15.2 ms | 29 ms |
| TC-MEM-01/budget | mem hog   @prio 10 | budget | 15 | 0/15 (0-20%) | pass | pass | MATCH | 8.1 ms | 25 ms |
| TC-KOB-01/none | fd exhaust@prio 10 | none | 15 | 0/15 (0-20%) | pass | pass | MATCH | 9.6 ms | 27 ms |
| TC-KOB-01/prio | fd exhaust@prio 10 | prio | 15 | 0/15 (0-20%) | pass | pass | MATCH | 32.1 ms | 48 ms |
| TC-KOB-01/isolate | fd exhaust@prio 10 | isolate | 15 | 0/15 (0-20%) | pass | pass | MATCH | 11.1 ms | 30 ms |
| TC-KOB-01/budget | fd exhaust@prio 10 | budget | 15 | 0/15 (0-20%) | pass | pass | MATCH | 6.0 ms | 24 ms |
| TC-PRC-01/none | crash loop@prio 10 | none | 15 | 0/15 (0-20%) | pass | pass | MATCH | 20.8 ms | 39 ms |
| TC-PRC-01/prio | crash loop@prio 10 | prio | 15 | 0/15 (0-20%) | pass | pass | MATCH | 31.6 ms | 50 ms |
| TC-PRC-01/isolate | crash loop@prio 10 | isolate | 15 | 0/15 (0-20%) | pass | pass | MATCH | 48.2 ms | 64 ms |
| TC-PRC-01/budget | crash loop@prio 10 | budget | 15 | 0/15 (0-20%) | pass | pass | MATCH | 9.2 ms | 27 ms |
| TC-PRC-02/none | crash loop@prio 20 | none | 15 | 0/15 (0-20%) | pass | pass | MATCH | 48.2 ms | 66 ms |
| TC-PRC-02/prio | crash loop@prio 20 | prio | 15 | 0/15 (0-20%) | pass | pass | MATCH | 18.7 ms | 30 ms |
| TC-PRC-02/isolate | crash loop@prio 20 | isolate | 15 | 0/15 (0-20%) | pass | pass | MATCH | 9.3 ms | 28 ms |
| TC-PRC-02/budget | crash loop@prio 20 | budget | 15 | 0/15 (0-20%) | pass | pass | MATCH | 4.7 ms | 23 ms |
| TC-SVC-01/none | kill detector, no supervisor | none | 15 | 15/15 (80-100%) | fail | fail | MATCH | 28.3 ms | 46 ms |
| TC-SVC-01/prio | kill detector, no supervisor | prio | 15 | 15/15 (80-100%) | fail | fail | MATCH | 16.2 ms | 34 ms |
| TC-SVC-01/isolate | kill detector, no supervisor | isolate | 15 | 15/15 (80-100%) | fail | fail | MATCH | 15.7 ms | 33 ms |
| TC-SVC-01/budget | kill detector, no supervisor | budget | 15 | 15/15 (80-100%) | fail | fail | MATCH | 3.3 ms | 21 ms |
| TC-SVC-02/none | kill detector, supervised | none | 15 | 0/15 (0-20%) | pass | pass | MATCH | 52.9 ms | 56 ms |
| TC-SVC-02/prio | kill detector, supervised | prio | 15 | 0/15 (0-20%) | pass | pass | MATCH | 22.8 ms | 41 ms |
| TC-SVC-02/isolate | kill detector, supervised | isolate | 15 | 0/15 (0-20%) | pass | pass | MATCH | 43.8 ms | 53 ms |
| TC-SVC-02/budget | kill detector, supervised | budget | 15 | 0/15 (0-20%) | pass | pass | MATCH | 3.8 ms | 41 ms |
| TC-BAS-02/none | memory bandwidth @prio 20 | none | 15 | 15/15 (80-100%) | fail | fail | MATCH | 5.0 s | 4993 ms |
| TC-BAS-02/prio | memory bandwidth @prio 20 | prio | 15 | 0/15 (0-20%) | pass | pass | MATCH | 20.4 ms | 37 ms |
| TC-BAS-02/isolate | memory bandwidth @prio 20 | isolate | 15 | 0/15 (0-20%) | pass | pass | MATCH | 19.0 ms | 32 ms |
| TC-BAS-02/budget | memory bandwidth @prio 20 | budget | 15 | 0/15 (0-20%) | pass | pass | MATCH | 28.9 ms | 46 ms |
| TC-BAS-03/none | timer storm @prio 20 | none | 15 | 0/15 (0-20%) | pass | pass | MATCH | 60.5 ms | 78 ms |
| TC-BAS-03/prio | timer storm @prio 20 | prio | 15 | 0/15 (0-20%) | pass | pass | MATCH | 20.7 ms | 38 ms |
| TC-BAS-03/isolate | timer storm @prio 20 | isolate | 15 | 0/15 (0-20%) | pass | pass | MATCH | 15.6 ms | 33 ms |
| TC-BAS-03/budget | timer storm @prio 20 | budget | 15 | 0/15 (0-20%) | pass | pass | MATCH | 4.8 ms | 23 ms |
| TC-BAS-04/none | kernel-call storm @prio 20 | none | 15 | 15/15 (80-100%) | fail | fail | MATCH | 9.9 ms | 25 ms |
| TC-BAS-04/prio | kernel-call storm @prio 20 | prio | 15 | 0/15 (0-20%) | pass | pass | MATCH | 16.7 ms | 32 ms |
| TC-BAS-04/isolate | kernel-call storm @prio 20 | isolate | 15 | 0/15 (0-20%) | pass | pass | MATCH | 26.0 ms | 43 ms |
| TC-BAS-04/budget | kernel-call storm @prio 20 | budget | 15 | 2/15 (4-38%) | pass | pass | MATCH | 173.5 ms | 190 ms |
| TC-BAS-05/none | memory bandwidth @prio 5 | none | 15 | 0/15 (0-20%) | pass | pass | MATCH | 51.7 ms | 68 ms |
| TC-BAS-05/prio | memory bandwidth @prio 5 | prio | 15 | 0/15 (0-20%) | pass | pass | MATCH | 15.4 ms | 33 ms |
| TC-BAS-05/isolate | memory bandwidth @prio 5 | isolate | 15 | 0/15 (0-20%) | pass | pass | MATCH | 30.5 ms | 45 ms |
| TC-BAS-05/budget | memory bandwidth @prio 5 | budget | 15 | 0/15 (0-20%) | pass | pass | MATCH | 51.8 ms | 42 ms |
| TC-BAS-06/none | kernel-call storm @prio 5 | none | 15 | 0/15 (0-20%) | pass | pass | MATCH | 7.0 ms | 24 ms |
| TC-BAS-06/prio | kernel-call storm @prio 5 | prio | 15 | 0/15 (0-20%) | pass | pass | MATCH | 6.3 ms | 24 ms |
| TC-BAS-06/isolate | kernel-call storm @prio 5 | isolate | 15 | 0/15 (0-20%) | pass | pass | MATCH | 11.4 ms | 29 ms |
| TC-BAS-06/budget | kernel-call storm @prio 5 | budget | 15 | 0/15 (0-20%) | pass | pass | MATCH | 79.4 ms | 95 ms |
| TC-BAS-07/none | memory bandwidth @prio 10 | none | 15 | 15/15 (80-100%) | fail | fail | MATCH | 107.1 ms | 99 ms |
| TC-BAS-07/prio | memory bandwidth @prio 10 | prio | 15 | 0/15 (0-20%) | pass | pass | MATCH | 15.2 ms | 33 ms |
| TC-BAS-07/isolate | memory bandwidth @prio 10 | isolate | 15 | 0/15 (0-20%) | pass | pass | MATCH | 14.7 ms | 31 ms |
| TC-BAS-07/budget | memory bandwidth @prio 10 | budget | 15 | 0/15 (0-20%) | pass | pass | MATCH | 27.7 ms | 45 ms |
| TC-BAS-08/none | name squat, detector alive | none | 10 | 0/10 (0-28%) | pass | pass | MATCH | 5.0 ms | 22 ms |
| TC-BAS-08/prio | name squat, detector alive | prio | 10 | 0/10 (0-28%) | pass | pass | MATCH | 4.6 ms | 22 ms |
| TC-BAS-08/isolate | name squat, detector alive | isolate | 10 | 0/10 (0-28%) | pass | pass | MATCH | 83.1 ms | 99 ms |
| TC-BAS-08/budget | name squat, detector alive | budget | 10 | 0/10 (0-28%) | pass | pass | MATCH | 9.8 ms | 28 ms |
| TC-BAS-09/none | name squat, race after restart | none | 10 | 10/10 (72-100%) | fail | fail | MATCH | 5.4 ms | 24 ms |
| TC-BAS-09/prio | name squat, race after restart | prio | 10 | 8/10 (49-94%) | fail | fail | MATCH | 4.8 ms | 40 ms |
| TC-BAS-09/isolate | name squat, race after restart | isolate | 10 | 10/10 (72-100%) | fail | fail | MATCH | 10.4 ms | 27 ms |
| TC-BAS-09/budget | name squat, race after restart | budget | 10 | 8/10 (49-94%) | fail | fail | MATCH | 5.5 ms | 40 ms |
| TC-BAS-10/none | name squat, race after restart (owner check) | none | 10 | 0/10 (0-28%) | pass | pass | MATCH | 3.4 ms | 41 ms |
| TC-BAS-10/prio | name squat, race after restart (owner check) | prio | 10 | 0/10 (0-28%) | pass | pass | MATCH | 3.1 ms | 41 ms |
| TC-BAS-10/isolate | name squat, race after restart (owner check) | isolate | 10 | 0/10 (0-28%) | pass | pass | MATCH | 8.3 ms | 41 ms |
| TC-BAS-10/budget | name squat, race after restart (owner check) | budget | 10 | 0/10 (0-28%) | pass | pass | MATCH | 3.6 ms | 41 ms |

## 4. Environment

* Target: QEMU emulation (aarch64le, virt machine, 2 CPUs, software emulation).
* Operating system: QNX SDP 8.0 (QNX Everywhere, non-commercial licence), toolchain `qcc -Vgcc_ntoaarch64le`.
* Tool revision: `e175c26 + uncommitted changes`. Raw runs: `docs/results/`.
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
