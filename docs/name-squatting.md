# Name squatting: who owns the detector's name?

The pipeline finds the detector by name (`name_attach` / `name_open`, which QNX resolves under
`/dev/name/local/`). The `squat` attacker registers the same name, receives whatever is sent to
it, and never replies. Two cases, measured on QNX SDP 8.0 in QEMU, 10 runs each, failed runs out
of 10:

| Case | No hardening | `prio` | `isolate` | `budget` |
|---|---|---|---|---|
| The detector is alive when the squatter starts | 0/10 | 0/10 | 0/10 | 0/10 |
| The detector is killed and restarted, squatter at priority 20 | **10/10** | **8/10** | **10/10** | **8/10** |
| Same, with the supervisor checking who owns the name (`-K`) | 0/10 | 0/10 | 0/10 | 0/10 |

(The full tables are in [`report.md`](report.md).)

## What happens

1. **While the detector is alive, QNX refuses the squatter.** A second `name_attach` for a name
   that is already taken fails with `File exists`. The squatter retried more than a thousand times
   in one run and only got the name when the run was ending and the detector exited.
2. **After the detector dies, the squatter races the restart, and wins.** It polls every
   millisecond; the supervisor needs a few milliseconds to respawn the detector. The restarted
   detector gets `File exists`, exits, and the supervisor respawns it again, more than twenty times
   in one run. The pipeline's frames go to the squatter, which swallows them, so the controller sees
   a silent pipeline.
3. **None of the CPU hardening helps.** A higher pipeline priority, its own CPU and a CPU budget
   for the attacker all leave the squatter polling and winning, because this is a naming race,
   not CPU contention. The two `8/10` rows are the cases where the restart happened to win a few
   times.
4. **The supervisor's own readiness check is fooled.** It counted the service as ready when
   `name_open` succeeded, which also succeeds against the squatter. It printed
   `death_to_ready_ms=1` for restarts in which no real detector was running. The restart times
   reported elsewhere (about 3 ms) are for the case where nothing is squatting.

## The mitigation, and what it costs

`supervisor -o` asks the kernel who owns the name (`ConnectServerInfo`, which returns the server's
process id) and counts the service ready only if that is the process it just started. `-K` also
kills a different process found holding the name. With `-K`, the squatter was killed on the first
restart and the pipeline recovered: 0 of 10 failed under every profile.

This is a real defence only under its assumptions:

* The supervisor must be allowed to kill the impostor (here it runs as root). An attacker with
  the same privileges and a faster respawn could keep winning, and killing an unknown process is
  itself a risky action in a real system.
* It does not stop a squatter that registers before the service ever starts; it would be caught
  at first start, but the supervisor would have to decide what to do about it.
* It is a test of one mechanism in an emulator, with one attacker. It says that checking the name's
  owner closes this race, not that names cannot be spoofed in other ways.

Files: `pipeline/attacker.c` (`squat`), `pipeline/supervisor.c` (`-o`, `-K`), the `NAME_DEFENCE=1`
variable in `image/pipeline.sh`, scenarios in `siege.json`, raw runs in `results/squat-*.json`.
