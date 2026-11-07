# Interference patterns

Each finding from the runs, written as a pattern you can recognise in your own
system: what you see, why it happens, how Siege shows it, and what fixes it
(and what does not). Counts are failed runs out of total runs, from
[`report.md`](report.md); every run is 5 seconds with a 20 ms deadline. All
timing is from QEMU emulation. Which mechanism belongs to QNX and which is
generic is discussed in [`why-qnx.md`](why-qnx.md).

| Pattern | Looks like | Fixed by |
|---|---|---|
| [1. Priority starvation](#1-priority-starvation) | seconds of silence, then one enormous latency | priority, own CPU, CPU budget |
| [2. Queue-priority starvation](#2-queue-priority-starvation) | repeated silences and lost frames, a quiet attacker | priority only |
| [3. Burst interference](#3-burst-interference) | periodic late frames, p99 equals the burst length | priority, own CPU, CPU budget |
| [4. Same-priority timeslice jitter](#4-same-priority-timeslice-jitter) | fails only with a tight deadline | priority |
| [5. A dead service with no supervisor](#5-a-dead-service-with-no-supervisor) | the stream stops and never resumes | a supervisor |
| [6. Priority inversion through a shared lock](#6-priority-inversion-through-a-shared-lock) | the pipeline blocks on a lock for seconds, then goes silent | a priority-inheriting mutex only |
| [7. Contained by process isolation](#7-contained-by-process-isolation) | nothing | (not a failure) |

## 1. Priority starvation

**Symptom.** The controller reports nothing for the whole attack, then one
huge latency when the attacker stops. In the live dashboard the tile turns to
STALLED. Median latency is seconds, about 80% of frames are late.

**Cause.** A thread at priority 20 that never blocks keeps both CPUs; threads
at priority 10 only run when it stops. This is strict fixed-priority
scheduling doing what it is designed to do.

**Seen.** `cpu hog @prio 20`, no hardening: **15/15 runs failed** in every 15-run
set. In one set the worst frame was 5.0 s with a longest silence of 5,010 ms; in the
latest full matrix the controller gave up after 3 s without a frame in 14 of 15 runs,
so no latency was reported. Both are total starvation. Under `prio`: 0/15. Under
`isolate`: 0/15. Under `budget`: 1/15 (one 66 ms spike).

**Detect.** `max_gap_ms` about as long as the attack, and a median latency in
seconds. It is the easiest pattern to see and the one most people expect.

**Fix.** Put the pipeline above its neighbours (`prio`), give it a CPU of its
own (`isolate`), or cap the neighbour with a CPU budget (`budget`). Any of the
three works for this pattern.

## 2. Queue-priority starvation

**Symptom.** The pipeline stops delivering frames in bursts: many short
silences of hundreds of milliseconds and many lost frames. The worst *delivered*
frame still looks fine (16 ms), and the attacker barely uses any CPU, so
nothing looks wrong on a CPU graph.

**Cause.** A shared service receives messages highest sender priority first,
and runs at the priority of the client it is serving. A client at priority 30
that sends the service expensive requests keeps it busy at priority 30, and
the pipeline's lower-priority requests wait behind them. The bottleneck is
the service's queue, not CPU time.

**Seen.** `workflood @prio 30`, no hardening: **15/15 failed** (longest
silence 522 ms, tens of silences per run). Under `prio`: 1/15. Under
`isolate`: **15/15 failed, with frames starved for up to 5 s**. Under
`budget`: **15/15 failed**.

**Seen in a real QNX service, not only in Siege's own detector.** A program
whose latency goes through QNX's `pipe` manager
([`examples/pipeprobe`](../examples/pipeprobe/), 5 ms deadline) failed **5 of 5
runs** when another process pushed pipe traffic at priority 30 (median token
latency about 290 ms, worst 913 ms). The same traffic at the probe's own
priority failed 0 of 5, and with the probe raised to priority 40 it failed 0 of
5. Unlike `workflood`, this attacker moves real data (about 10 MB/s), so it is
not a "quiet" attacker; the queue ordering is what the two have in common.

**Detect.** `OUTAGE` events and lost frames while the worst delivered frame
stays small. If the verdict is FAIL but the latency chart looks healthy, look
at the lost-frame count and at which clients talk to the shared service.

**Fix.** Raise the pipeline's priority above every client of the shared
service (`prio`). **Not fixed by** giving the pipeline its own CPU, and **not
fixed by** capping the attacker's CPU: it uses almost none, and the damage
happens in a queue that CPU isolation does not touch. This is the finding
that depends most on how QNX message passing works.

## 3. Burst interference

**Symptom.** Periodic late frames. The median latency is normal, but p99 is as
long as the neighbour's compute burst, and the late fraction roughly matches
the neighbour's share of the CPU.

**Cause.** A well-meaning compute workload at a higher priority preempts the
pipeline for the length of each burst. Nothing is hostile; the workload is
simply scheduled above the pipeline.

**Seen.** `AI neighbour @prio 20` (40 ms of matrix multiplication every
100 ms), no hardening: **15/15 failed**, 573 late frames out of 3,750 (about
15%), worst frame 44 ms, median 2.5 ms. The same neighbour at priority 10:
**0/15**. Under `prio`, `isolate` and `budget`: 0/15 each.

**Detect.** p99 close to the burst length with a normal median, and failures
that disappear when the neighbour's priority is lowered. The bug is the
priority, not the workload.

**Fix.** Any of the three profiles. The cheapest is to make sure inference-style
jobs run below the safety pipeline.

## 4. Same-priority timeslice jitter

**Symptom.** A program with a tight deadline fails against neighbours at the
*same* priority, while a program with a slack deadline does not.

**Cause.** Round-robin threads at one priority share the CPU in timeslices. A
thread that wakes up waits for the running one's slice to end, which costs
milliseconds. That is invisible against a 20 ms deadline and fatal against 5 ms.

**Seen.** The reference pipeline (20 ms) at the same priority as a CPU hog:
8/15, 9/15 and 11/15 failed with no hardening in three separate 15-run sets (an earlier
5-run check showed 0/5, so the effect is unstable under emulation), and 0/15 at a higher priority. The `ticker` example (5 ms, [`examples/ticker`](../examples/ticker/)):
**3/3 failed** against a same-priority CPU hog and against a crash loop. With
the ticker at priority 40: 0/3.

**Detect.** Failures that appear only when the deadline is tightened, with
neighbours at your own priority. Run Siege with your real deadline.

**Fix.** A higher priority than the neighbours.

## 5. A dead service with no supervisor

**Symptom.** The stream stops at some moment and never resumes. The controller
gives up after 3 s of silence.

**Cause.** A pipeline stage died and nothing replaced it. This is not a
scheduling problem, so no scheduling profile can help.

**Seen.** `kill detector, no supervisor`: **15/15 failed under all four
profiles**. With the supervisor: 0/15 under every profile.

**Detect.** A run that ends with `abandoned=1`: the controller stopped hearing
from the pipeline altogether.

**Fix.** A supervisor that restarts the stage. In emulation the detector was
serving again within a few milliseconds (median 5 ms over 15 runs), and the
controller's worst silence was 41 ms.

## 6. Priority inversion through a shared lock

**Symptom.** The pipeline delivers a few frames and then goes silent. Nothing
is overloaded: the CPUs are busy with the neighbours, and the pipeline is
simply waiting. The detector's wait for the lock is as long as the attack.

**Cause.** A low-priority process holds a lock the pipeline needs, and
medium-priority work keeps the holder from running to release it, so the
high-priority pipeline waits behind work that is below it. This is the
mechanism behind the 1997 Mars Pathfinder resets (see
[`why-qnx.md`](why-qnx.md)).

**Seen.** `priority inversion (plain mutex)` failed **15 of 15 runs under every
profile**: no hardening, `prio` (pipeline at priority 40), `isolate` and
`budget`. In an instrumented run the detector's longest wait for the lock was
about 4.95 s and the pipeline never recovered. With a `PTHREAD_PRIO_INHERIT`
mutex the same scenario passed in 59 of 60 runs (one failure of 15 with no hardening), with a longest
wait of about 3 ms. The **system default** mutex passed 60 of 60 across the four
profiles: on QNX the unsafe protocol (`PTHREAD_PRIO_NONE`) has to be chosen
explicitly.

**Detect.** The detector prints `DET shared lock: ... longest wait` at the end
of a run; a wait as long as the attack, with `abandoned=1`, is the signature.
The failure does not respond to priority, affinity or CPU budgets.

**Fix.** Use a priority-inheriting mutex for every lock the pipeline shares
with other processes. **Not fixed by** raising the pipeline's priority, giving
it a CPU of its own, or capping the other processes' CPU: the holder is the
thing that cannot run, and none of those make it run.

## 7. Contained by process isolation

These did **not** break the unhardened pipeline at the default priority:

* a process holding and touching 300 MB,
* a process exhausting its descriptors, channels and connections (997, 100 and
  65,533 in our runs),
* a process crashing and being restarted about 1,800 times in seven seconds,
* a plain flood of junk messages to the detector, which rejects them.

Each was run 5 times with no failure. That is *not observed*, not *cannot
happen*: zero failures in 5 runs is consistent with a failure rate up to about
43%. Run more repeats, and at your own priorities, before relying on it.

## Reading Siege's output

| You see | It points to |
|---|---|
| Median latency in seconds; `max_gap_ms` as long as the attack | Pattern 1 |
| `OUTAGE` events, lost frames, a healthy-looking worst frame | Pattern 2 |
| p99 near a burst length, normal median, periodic late frames | Pattern 3 |
| Fails only at a tight deadline, neighbours at your priority | Pattern 4 |
| `abandoned=1` | Pattern 5, or pattern 6 if `DET shared lock` shows a very long wait |
| A `DET shared lock` wait as long as the attack | Pattern 6 |
| `wrong` above 0 in the `FINAL` line (trained-network mode) | The model answered incorrectly: a correctness problem, not a timing one |
