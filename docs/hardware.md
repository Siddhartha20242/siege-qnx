# Running Siege on real hardware

Every result in this repository was measured in QEMU. That is the biggest
caveat on it: emulated timing is not hardware timing. The large effects (a
multi-second starvation, silences of hundreds of milliseconds) are far above
the emulator's noise, but nobody should have to take our word that they
reproduce on a real board.

Siege runs on real hardware without the QEMU image. Its programs are ordinary
aarch64 QNX executables and its launch scripts are plain `ksh`, so they can be
copied to any QNX 8.0 aarch64 target and driven over `ssh`. **This path has
not been run on hardware yet.** The transport and the installer were tested
against a stand-in machine; the rest is untested, and this page says so so
that whoever tries it first knows.

## What you need

* A QNX 8.0 target with at least two CPU cores. A Raspberry Pi 4 or 5 running
  the QNX Quick Start Target Image for Raspberry Pi fits. The `isolate` profile
  uses CPU 0 and CPU 1.
* `sshd` running on it, and key-based login from your computer
  (`ssh-copy-id user@target`). Siege never asks for a password.
* `ksh` at `/bin/ksh` and the `on` utility, which standard QNX images have.
* A built Siege (`./siege build`), so that `build/bin` holds the aarch64
  programs.
* Free RAM: the `mem` attacker holds 300 MB. On a board with 1 GB, close other
  things or skip that scenario.

## Run it

```sh
./siege hw install root@TARGET        # copies the programs and scripts to /data/siege and checks them
./siege test --ssh root@TARGET --profile none    --json hw-none.json
./siege test --ssh root@TARGET --profile prio    --json hw-prio.json
./siege test --ssh root@TARGET --profile isolate --json hw-isolate.json
./siege test --ssh root@TARGET --profile budget  --json hw-budget.json
./siege report hw-none.json hw-prio.json hw-isolate.json hw-budget.json --out hw-report
```

Use `--only "cpu hog   @prio 20"` (repeatable) to run a subset first, and
`--runs` to change the number of runs per scenario.

On hardware Siege switches off the emulator workaround (`IDLE_POLL=0`): the
priority-1 spinner exists only to hide QEMU's cost of waking an idle virtual
CPU, and real CPUs do not have that cost.

## What to look for

The claims worth testing, in order of how much they matter:

1. A CPU hog at priority 20 starves the unhardened pipeline, and every profile
   restores it.
2. `workflood` at priority 30 breaks the pipeline, and **only the `prio`
   profile** fixes it. `isolate` and `budget` do not.
3. The AI neighbour at priority 20 fails the unhardened pipeline and passes
   under every profile; at the default priority it is harmless.
4. A killed detector is never replaced without the supervisor, and is back
   within milliseconds with it.
5. Memory, descriptor exhaustion, crash loops and the plain message flood at
   the default priority do not break the pipeline.

If the deadline (20 ms) is wrong for your board, run `./siege calibrate`
first. It measures the clean pipeline and suggests a deadline. (It runs in
QEMU; for hardware, run a few clean runs with
`./siege test --ssh ... --only baseline --runs 10` and read the worst frame.)

## Sharing a result

Please open an issue titled "Hardware results: <board>" with:

* the board and QNX version,
* the `hw-*.json` files (or the `hw-report.md` that `./siege report` wrote),
* anything that failed to run, with the command and its output.

A report generated from hardware runs is labelled "real hardware" in its
header, and hardware and emulator results should be reported separately, not
merged.

## Hardware results so far

None. This table will list them as they come in.

| Board | QNX | Who ran it | Matches the emulator? |
|---|---|---|---|
| | | | |
