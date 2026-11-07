# Why QNX: what the measurements say

Siege exists because a real-time system has to keep its deadlines while other
software misbehaves. This page ties each result to the QNX mechanism behind
it, and says plainly which results are about QNX and which would hold on any
fixed-priority scheduler. Exact counts are in [`report.md`](report.md).

## Why this kind of testing exists

In 1997 the Mars Pathfinder lander began resetting its own computer after it
reached Mars. The software team at JPL traced it to priority inversion: a
low-priority task held a mutex that a high-priority task needed, and
medium-priority tasks kept the low-priority one from running, so the
high-priority task waited. The mutex had been created without priority
inheritance, and the fix was to turn that setting on. See the JPL software
lead's own account,
[What really happened on Mars Rover Pathfinder](https://www.cs.cornell.edu/courses/cs614/1999sp/papers/pathfinder.html),
and [his email to the mailing list](https://www.cs.cornell.edu/courses/cs614/1999sp/papers/pathfinder2.html).

The lesson was not that anyone was careless. A real-time system's behaviour
under interference depends on settings and neighbours that look harmless one at
a time. Siege exists to try those combinations on purpose, and its
priority-inversion scenario (pattern 6 in [`patterns.md`](patterns.md))
reproduces the same structure on QNX.

## Findings that depend on how QNX works

**1. Message queues are ordered by the sender's priority, and the server runs
at its client's priority.**
`workflood` sends the shared detector expensive requests from priority 30,
above the camera at priority 10. QNX delivers messages to a server highest
sender priority first, and the server runs at the priority of the client it is
serving. So the camera's frames wait behind the flood, and the pipeline stops
delivering frames, while the attacker itself barely uses any CPU.
Only raising the pipeline's priority fixed it. Giving the pipeline its own CPU
and capping the attacker's CPU did not, because the bottleneck is the shared
server's queue, not CPU time.
The same pattern appears in an unmodified QNX system service: a program whose
latency goes through the `pipe` manager failed 5 of 5 runs when another process
pushed pipe traffic at a higher priority, and passed once its own priority was
raised.
This is a documented design property of QNX message passing. It is what makes
priority reasoning across processes possible, and also what Siege tests for:
the property is only safe if every client of a shared service is trusted to
run below the pipeline.

**2. A mutex that does not inherit priority reproduces the Pathfinder failure,
and QNX's default mutex does inherit.**
In the priority-inversion scenario a low-priority process takes a lock the
pipeline needs, and hogs at a medium priority keep it from running. With a
mutex created with `PTHREAD_PRIO_NONE` the detector waited for the lock for
almost five seconds and the pipeline never recovered (15 of 15 runs, under every
profile). With `PTHREAD_PRIO_INHERIT` the longest wait was about three
milliseconds (59 of 60 runs passed across the four profiles). The **system default** mutex
behaved like the inheriting one, also 0 of 5 under every profile, so on QNX the
unsafe case has to be chosen on purpose. Raising the pipeline's priority did not help,
nor did giving it its own CPU or capping the hogs: only the inheriting mutex
did, as it did on Pathfinder.

**3. Faults stay inside their process.**
At the default priority the pipeline kept its deadlines against a process
holding 300 MB and touching it, a process exhausting its descriptors, channels
and connections (997, 100 and 65,533 in our runs), and a process crashing and
restarting about 1,800 times in seven seconds. None of those broke the
pipeline. QNX runs services and drivers as ordinary user-space processes, so a
failure is confined to the process that has it. This is a statement about
those attacks, not a proof that nothing can interfere (see the confidence
bounds in the report).

**4. Services are restarted from outside, quickly.**
A killed detector is restarted by a small supervisor built on `spawnvp` and
`waitpid`. In emulation it was serving again within a few milliseconds and the
controller saw a gap of tens of milliseconds. Without a supervisor nothing
replaces it and the pipeline goes quiet for good.

**5. A service can be a file.**
`sieged` is a resource manager: `cat /dev/siege` returns the pipeline's live
status, and the controller pushes updates to it over ordinary message passing.
The same pathname space and the same message primitives serve both file I/O
and our own protocol, in one dispatch loop of about a hundred lines.

**6. The image is small and ours.**
`mkifs` builds the whole bootable system, kernel, startup code, drivers,
libraries and the pipeline, into a roughly 4 MB image that boots in seconds
and runs from RAM. Every process in it is one we chose.

## Findings that are not specific to QNX

* A CPU hog at a higher priority than the pipeline starves it, under any
  strict fixed-priority scheduler.
* A periodic compute neighbour (the `ai` attacker) delays a lower-priority
  pipeline in proportion to its bursts, wherever it runs.
* Per-thread CPU budgets (`SCHED_SPORADIC`) are part of POSIX. QNX implements
  them, and they restored the CPU-hog and AI-neighbour cases.
* CPU affinity separates CPU contention, and nothing else.

## What the measurements do not show

* No other operating system was measured, so nothing here says QNX does
  better than anything else. It says which mechanisms mattered on QNX.
* All timing is from QEMU and is not hardware timing.
* The pipeline and its frames are synthetic, so that every run sees identical
  input.
