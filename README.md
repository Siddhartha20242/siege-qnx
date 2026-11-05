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

`attacker` runs one of five attacks against the live pipeline:

| Mode | Behaviour |
|---|---|
| `cpu` | Threads that spin and never block |
| `mem` | Allocates and keeps touching 300 MB |
| `flood` | Sends junk messages to the detector as fast as it can |
| `fd` | Exhausts file descriptors, channels and connections |
| `crash` | Spawns a child that segfaults, and restarts it immediately |

## Hardening profiles

Set with `PROFILE=` in `image/pipeline.sh`.

| Profile | QNX mechanism | Effect |
|---|---|---|
| `none` | Default round-robin, priority 10 for everything | Baseline |
| `prio` | Fixed priorities | Pipeline at 40, above its neighbours |
| `isolate` | CPU affinity (`on -C`) | Pipeline owns CPU 1; attackers are confined to CPU 0 |
| `budget` | `SCHED_SPORADIC` | Attackers are capped at 10 ms of CPU per 100 ms, even at a higher priority |

## Result

A CPU hog at priority 20 against a pipeline at priority 10 (5-second runs,
15 ms deadline, 2% late-frame tolerance, three runs per profile):

| Profile | Runs passed | Late frames | Median latency |
|---|---|---|---|
| `none` | 0 / 3 | 80% | about 2,580 ms |
| `prio` | 3 / 3 | 0% | about 2 ms |
| `isolate` | 3 / 3 | 0% | about 2 ms |
| `budget` | 3 / 3 | 0.4 to 0.8% | about 4 ms |

Without hardening, the pipeline is starved for the whole attack. With any of
the three profiles it keeps its deadlines.

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
scripts/matrix.py --profile none --runs 4     # every attack, repeated
scripts/matrix.py --profile prio --runs 4
```

`image/ram.build` contains absolute paths to the SDK and the build output on
the build machine (`/home/siddhartha07/...`); change them to match your
account.

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
* Not yet built: a supervisor with recovery-time measurement, a `/dev/siege`
  resource manager, a host dashboard and generated report, and a config file
  to point Siege at other pipelines.

## Licence

MIT. See `LICENSE`.
