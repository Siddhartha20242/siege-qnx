# Independent code review of the C programs

A reviewer that had not seen our reasoning read every file in [`pipeline/`](../pipeline/)
and was asked for defects with concrete failure scenarios, not style. It could not run
QNX, so every finding below is from reading the code; the ones marked "unverified on
QNX" depend on how the QNX libraries behave and we have not tested them. This page
lists each finding, what we did, and what it means for the published results.

## Fixed

| # | Finding | Change |
|---|---|---|
| 7 | The detector and controller trusted any message length, so a short message re-used stale fields | Both check `_msg_info.msglen` and reject (`MsgError`) or skip short messages |
| 8 | The controller's give-up check ran only on a receive timeout, so a process sending a stray message every 100 ms kept a dead pipeline "alive" for ever | The check also runs on every non-frame message |
| 9 | `/dev/siege` cast a 64-bit read offset to `int`, so a reader could seek to a huge offset and read before the buffer | The offset is compared before it is narrowed |
| 10 | `sieged` did not check the length of a status message | Short messages are rejected |
| 5 | `frame_src` divided before multiplying, so `-p 30 -d 10` sent 330 frames instead of 333 | Multiply first. The default 30 Hz run gives the same count as before |
| 15 | `siegewrap` could wait for ever on a child that ignored `SIGTERM` | It waits up to 2 s, then sends `SIGKILL` |

None of these changes what the controller counts or when it declares PASS or FAIL for
the scenarios in the published matrix. After rebuilding, a subset was re-run to check that
(next section).

## Known, not changed

These are real. We did not change them because doing so would change what a published
number means, or because they need QNX to settle.

| # | Finding | Why it stays | Effect on our claims |
|---|---|---|---|
| 1 | Frames dropped inside a silence of 100 to 500 ms count as an "outage", which the PASS/FAIL verdict only judges by the length of the longest gap | Changing the verdict would change every published row | We checked all 4,441 recorded runs: only **2** passed while containing an outage (a 104 ms gap each, `workflood` at priority 30 under `prio`). The rows are not affected in any visible way, but a pattern of repeated 100-500 ms silences would be under-reported |
| 2 | After a long silence the per-second summaries are mislabelled or duplicated | Only the printed windows and the monitor's features, not the totals | The learned monitor's inputs can be wrong after a silence. Its negative result stands, but it was not tested against this |
| 3 | Frames dropped after the last delivered frame, and the final silence, are not counted | The controller is not told how many frames were sent; fixing it means a protocol change | Possible under-count of loss at the end of a run. Attackers run 1 s longer than the camera, so it is realistic |
| 4 | Frames lost before the first frame count as `lost`, while the same loss mid-run counts as an outage | Same as 1 | Affects only runs with `ATK_DELAY=0`; the published runs use 1 s |
| 6 | Percentiles use at most 65,536 samples | Runs here are 5 s | None |
| 11 | Reply timeouts may not fire on a client already waiting, because `name_attach` may set the unblock flag and the servers ignore the pulse; disconnect pulses are not answered, so connections leak | Two independent reviewers believe this is documented QNX behaviour; we have **not tested it**, so treat it as likely true | If true, the squatter holds the camera blocked for the whole squat rather than 5 ms, and `workflood`'s timeout count is understated. The pass and fail outcomes of those scenarios would not change |
| 12 | The process-shared mutex used by the inversion attacker is not robust and has a start-up race | The attacker is a test fixture | None for results; a killed attacker could hang the detector |
| 13 | The monitor thread reads data the main loop writes without proper ordering | Low impact, off by default | Possible half-updated features in the monitor |
| 14 | Attacker statistics counters are not atomic and can undercount | The counters are informational | `prio_denied` can read 1 when two threads were denied; it is never used to decide a result |
| 16 | The supervisor's owner check passes if it cannot read the owner | Matches the intended fallback | The check is weaker than it sounds when the lookup fails |

## What the reviewer checked and found sound

Receive buffers are the size of their targets. The percentile code guards an empty set and
clamps its index, and the verdict uses 64-bit arithmetic. The detector's filter and
network loops stay in bounds. `MSG_WORK` passes are capped. `name_open` and
`name_attach` results are checked correctly. The launch order in `pipeline.sh` has no
start-up race.

## What this does not cover

It is one reviewer reading, not a proof, and nothing here was exercised under a sanitizer
or fuzzer. A human QNX engineer reading the same files would very likely find more.

## Regression check after the fixes

Nine scenarios (baseline, CPU hog at 20, `workflood` at 30, the AI neighbour, both kill
scenarios and all three name-squat scenarios) were re-run, 10 runs each, under `none`
and `prio`, on the rebuilt image ([`docs/results/regress-none.json`](results/regress-none.json),
[`regress-prio.json`](results/regress-prio.json)). Every cell kept its published outcome:
the ones that failed every run still fail every run, the ones that passed still pass.
The one cell that moved is the name squat under `prio`, 9 of 10 failing against a published
8 of 10, which is within the scatter of ten runs. Only 18 of the matrix's 104 cells (26 scenarios, 4 profiles) were
re-run on the fixed code, so this is a spot check, not a full replay.
