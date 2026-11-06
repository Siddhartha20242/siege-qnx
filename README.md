# Siege

Stress-testing for real-time isolation on QNX 8.0.

A real-time pipeline is only as safe as its worst neighbour. Siege runs a
camera-to-steering pipeline on QNX, attacks it with misbehaving processes
(a CPU hog, a message flood, memory and descriptor exhaustion, a crash loop),
measures every frame against its deadline, and shows how QNX scheduling
features restore the deadlines. The same attack can be replayed with and
without a hardening profile, so the effect of each QNX mechanism is measured,
not assumed.

Siege produces stress evidence and regression tests. It does not certify
anything: passing runs show an isolation setup survived the attacks tried, not
that it is free from interference in general.

## Target

| | |
|---|---|
| OS | QNX SDP 8.0 (QNX Everywhere, non-commercial licence) |
| Target | aarch64le on QEMU `virt` (`-machine virt,gic-version=3 -cpu cortex-a57 -smp 2`, software emulation) |
| Toolchain | `qcc -Vgcc_ntoaarch64le` (GCC 12.2.0) |
| Host used | macOS on Apple Silicon (runs QEMU) plus an Ubuntu ARM VM running the x86 QNX host tools under Rosetta |

The project builds and runs on any host that can run the QNX SDP and
QEMU. On x86_64 Linux the VM step is unnecessary: run `make` and `mkifs`
locally.

## What runs on QNX

Three processes talk over native QNX message passing:

```
frame_src --MsgSend--> detector --MsgSend--> controller
```

* `frame_src` stamps a deterministic synthetic 32x32 frame every 20 ms (50 Hz)
  with its scheduled capture time.
* `detector` is a small fixed-weight 3x3 detector that finds a moving object.
* `controller` computes a steering command and measures capture-to-command
  latency for every frame. Frames later than the deadline (15 ms by default),
  frames that never arrive, and a starved controller all count as failures.

`attacker` runs one of six attacks against the live pipeline:

| Mode | Behaviour |
|---|---|
| `cpu` | Threads that spin and never block |
| `mem` | Allocates and keeps touching 300 MB |
| `flood` | Sends junk messages to the detector as fast as it can |
| `workflood` | Sends the detector requests that each cost real CPU |
| `fd` | Exhausts file descriptors, channels and connections |
| `crash` | Spawns a child that segfaults, and restarts it immediately |

Two more processes support the pipeline:

* `supervisor` starts the detector, restarts it when it dies, and prints how
  long each restart took. It can also kill the detector on a schedule, to test
  recovery (`KILL_AT=<seconds>`, with `SUPERVISE=1` to restart it).
* `sieged` is a resource manager that publishes the live status as
  `/dev/siege`. The controller pushes a status line to it every second over
  native message passing, and `cat /dev/siege` returns the latest one, for
  example `state=GREEN t=4 profile=none frames=49 late=0 ...`.

## Hardening profiles

Set with `PROFILE=` in `image/pipeline.sh`.

| Profile | QNX mechanism | Effect |
|---|---|---|
| `none` | Default round-robin, priority 10 for everything | Baseline |
| `prio` | Fixed priorities | Pipeline at 40, above its neighbours |
| `isolate` | CPU affinity (`on -C`) | Pipeline owns CPU 1; attackers are confined to CPU 0 |
| `budget` | `SCHED_SPORADIC` | Attackers are capped at 10 ms of CPU per 100 ms, even at a higher priority |

## Result

All twelve scenarios were run against all four profiles, three runs each
(5-second runs, 15 ms deadline, 2% late-frame tolerance). The full table and
generated findings are in [`docs/report.md`](docs/report.md) and
[`docs/report.html`](docs/report.html); the raw runs are in `docs/results/`.

A CPU hog at priority 20 against a pipeline at priority 10:

| Profile | Failed runs | Median latency |
|---|---|---|
| `none` | 3 / 3 | about 2,530 ms |
| `prio` | 1 / 3 (one run with a 162 ms spike) | about 1.4 ms |
| `isolate` | 0 / 3 | about 1.8 ms |
| `budget` | 0 / 3 | about 3.4 ms |

Without hardening, the pipeline is starved for the whole attack. Every profile
restores it.

The other attacks at the default priority (CPU hog, message flood, memory
hog, descriptor exhaustion, crash loop) did not break the unhardened
pipeline: QNX contained them. One flood run out of three showed a 61 ms
spike, which also appears in clean runs under emulation.

### An attacker that uses no CPU

`workflood` burns almost no CPU itself. It sends the detector requests that
cost real work, from a priority above the pipeline's. The detector serves
higher-priority senders first and runs at the priority of the client it is
serving, so the camera's frames (priority 10) wait behind the flood
(priority 30). Failed runs out of three:

| Profile | Failed runs |
|---|---|
| `none` | 3 / 3 |
| `prio` | 0 / 3 |
| `isolate` | 3 / 3 |
| `budget` | 3 / 3 |

Only raising the pipeline's priority fixes it. Giving the pipeline its own CPU
does not, and neither does capping the attacker's CPU, because the attacker
barely uses any: the damage is done through the shared detector's message
queue. Each mitigation covers a different failure, which is why Siege tests
them against each attack instead of assuming one is enough.

### Recovery

With the detector killed two seconds in, three runs each:

| Setup | Result |
|---|---|
| No supervisor | Fails 3 / 3. The detector is never replaced; the controller gives up after 3 s of silence. No scheduling profile changes this. |
| `SUPERVISE=1` | Passes 3 / 3. The detector was serving again 6 ms after it died (median); the controller's worst silence was 41 ms. |

The controller reports silences longer than 100 ms as `OUTAGE` lines, and a
run also fails if any silence exceeds the recovery budget (500 ms by default).

## Build and run

Prerequisites: QNX SDP 8.0 installed (free through QNX Everywhere), QEMU, and
SSH access to a Linux machine with the SDP if your host cannot run the QNX
tools directly.

```sh
export SIEGE_VM=user@host        # machine with the QNX SDP in ~/qnx800
scripts/build.sh                 # sync, cross-compile, build build/siege.ifs
scripts/run.sh -n                # boot it; quit QEMU with Ctrl-A then x
```

At the QNX prompt:

```sh
pipeline.sh 8                                   # clean run, 8 seconds
ATK=cpu ATK_PRIO=20 pipeline.sh 8               # attacked, no hardening
PROFILE=budget ATK=cpu ATK_PRIO=20 pipeline.sh 8  # attacked, hardened
```

Each run prints one line per second, then a `FINAL` summary and
`RESULT PASS` or `RESULT FAIL`.

Automated runs from the host:

```sh
scripts/qnxrun.py "PROFILE=prio ATK=cpu ATK_PRIO=20 pipeline.sh 5"
scripts/calibrate.py                                        # measure the noise floor, suggest a deadline
scripts/matrix.py --profile none --json none.json           # every scenario in siege.json, repeated
scripts/matrix.py --profile prio --json prio.json
scripts/report.py none.json prio.json --out report          # report.md and report.html
```

Scenarios, run counts, the deadline and the tolerance live in `siege.json`:
to test a new attack or fault, add an entry to its `scenarios` list.

`calibrate.py` runs the clean pipeline repeatedly with a very large deadline
and reports the worst frame it saw. On the setup used here, ten clean runs had
a median latency of 1.5 ms and a worst single frame of 12.2 ms, and it
recommended a 20 ms deadline. The 15 ms deadline used for the reported results
sits closer to that noise than the recommendation, which is why the verdict
uses a 2% late-frame budget instead of requiring zero misses.

`report.py` writes a Markdown report and a self-contained HTML dashboard. The
findings in it are fixed rules over the measured numbers, so the same data
always gives the same report.

`image/ram.build` finds the SDK through `${QNX_TARGET}` (set by
`qnxsdp-env.sh`) and the build output relative to the repository root, so it
needs no editing.

New to QNX on a Mac? The [codelab](docs/codelab-qnx-on-apple-silicon.md)
walks through the whole setup from nothing: a free Ubuntu VM, the QNX SDP,
cross-compiling a native program, and booting it in QEMU.

## Testing your own program

Siege can attack any real-time program, not only the reference pipeline. The
generic launcher `image/harness.sh` starts your program, lets it settle for a
second, and then starts the attackers against it.

1. Build your program for QNX and add it to the image (`image/ram.build`).
2. Make it print the two lines Siege reads when it finishes:

   ```
   FINAL ... late=N lost=N stalls=N p50_us=N p99_us=N max_us=N
   RESULT PASS|FAIL
   ```

   Measure lateness against when each cycle was *due*, not when your code got
   to run, so that a starved program cannot hide its own starvation.
3. Describe the run in a config file: the command (`{dur}` is the run length),
   the profiles as environment variables your program reads, and the
   scenarios. [`examples/ticker/siege.json`](examples/ticker/siege.json) is a
   complete example.
4. Run it:

   ```sh
   scripts/matrix.py --config examples/ticker/siege.json --profile none --json none.json
   scripts/matrix.py --config examples/ticker/siege.json --profile prio --json prio.json
   scripts/report.py none.json prio.json --out report
   ```

[`examples/ticker/ticker.c`](examples/ticker/ticker.c) is a second program, a
single 100 Hz periodic task with a 5 ms deadline, about seventy lines long.
Siege tests it with no changes to the attackers. It is more fragile than the
reference pipeline, which shows that the result is specific to each program
(failed runs out of three; report in [`examples/ticker/`](examples/ticker/)):

| Attack | Default priority | Ticker at priority 40 |
|---|---|---|
| CPU hog at the same priority | 3 / 3 | 0 / 3 |
| CPU hog at priority 20 | 3 / 3 | 0 / 3 |
| Crash loop at priority 20 | 3 / 3 | 0 / 3 |

The reference pipeline survived the same-priority hog and the crash loop. The
ticker did not, because its deadline is tighter and it has no slack.

## Where QNX is used

* Native IPC: `name_attach`, `name_open`, `MsgSend`, `MsgReceive`,
  `MsgReply`, `MsgError` (`pipeline/*.c`)
* Bounded blocking calls: `TimerTimeout` on send, reply and receive
  (`pipeline/common.h`, `pipeline/controller.c`)
* Scheduling: `SCHED_RR`, `SCHED_SPORADIC`, `ThreadCtl(_NTO_TCTL_RUNMASK)`,
  `on -p`, `on -C` (`pipeline/attacker.c`, `pipeline/probe.c`,
  `image/pipeline.sh`)
* Kernel objects: `ChannelCreate`, `ConnectAttach`, `spawnl`
  (`pipeline/attacker.c`)
* Resource manager: `resmgr_attach`, `iofunc`, `message_attach` and
  `name_attach` on one dispatch loop, serving `/dev/siege`
  (`pipeline/sieged.c`)
* Process supervision: `spawnvp`, `waitpid`, `kill` (`pipeline/supervisor.c`)
* Boot image: custom `mkifs` buildfile with `startup-qemu-virt`,
  `procnto-smp-instr`, a startup script and the pipeline binaries, run
  entirely from RAM (`image/ram.build`)
* Diagnostics: `pidin`, `slogger2`

## How the measurements are kept honest

* Frames are stamped with their scheduled capture time, so a starved camera
  shows up as latency instead of hiding itself.
* The pipeline starts first and is attacked while it is running. An attacker
  started before the camera can starve it before its first timestamp.
* Emulation adds about 3 ms to every wake-up of an idle virtual CPU. A
  priority-1 spinner per CPU keeps them awake without taking time from
  anything at priority 2 or above (`IDLE_POLL=1`, default). It lowers the
  median latency from about 5.6 ms to about 2 ms.
* Emulation also produces rare isolated outliers, so the verdict is a late
  frame budget (2% by default) rather than zero misses, and results are
  reported as failure rates over repeated runs.

## Limitations

* QEMU timing is not hardware timing. Compare runs under identical
  conditions; do not read absolute latencies as hardware numbers.
* The detector and the frames are synthetic.
* Adaptive partitioning is not part of the free SDP, so it is not used.
* Results are from a handful of runs per scenario. Compare failure rates, not
  single runs.
* A program under test must print the `FINAL` and `RESULT` lines described
  above and be added to the image by hand; there is no loader for arbitrary
  binaries yet.

## Licence

MIT. See `LICENSE`.
