# Testing your own program

Siege can attack any real-time program, not only the reference pipeline. The
generic launcher `image/harness.sh` starts your program, lets it settle for a
second, and then starts the attackers against it.

1. Build your program for QNX and add it to the image: copy
   `image/local.build.example` to `image/local.build` and list your binary
   there. `scripts/build.sh` appends it to `image/ram.build`.
2. Make it print the two lines Siege reads when it finishes:

   ```
   FINAL ... late=N lost=N stalls=N p50_us=N p99_us=N max_us=N
   RESULT PASS|FAIL
   ```

   Measure lateness against when each cycle was *due*, not when your code got
   to run, so that a starved program cannot hide its own starvation.
3. Describe the run in a config file: the command (`{dur}` is the run length),
   the profiles as environment variables your program reads, and the
   scenarios. [`examples/ticker/siege.json`](../examples/ticker/siege.json) is a
   complete example.
4. Run it:

   ```sh
   scripts/matrix.py --config examples/ticker/siege.json --profile none --json none.json
   scripts/matrix.py --config examples/ticker/siege.json --profile prio --json prio.json
   scripts/report.py none.json prio.json --out report
   ```

**If you cannot change the program**, wrap it. `siegewrap` runs your command at a
chosen priority and, beside it, a canary task that measures how late it wakes
against when it was due. It also checks the program is still alive at the end or
exited with status 0, and prints the two lines Siege reads for you:

```json
{"pipeline": {"command": "siegewrap -d {dur} -p 10 -- ./your_program"}}
```

It sees scheduling pressure and crashes, not the program's own deadlines, message
queues or locks, so a pass means the program got the scheduling it needed, not that
its output was on time. [`examples/wrap/`](../examples/wrap/) runs it against a plain
shell loop (no failures at baseline, 5/5 failed against a CPU hog at the same
priority, 0/5 at priority 40). `-x ms` adds a whole-job deadline for programs that are meant to
finish: [`examples/wrap/siege-job.json`](../examples/wrap/siege-job.json) runs 200 calls of QNX's own `pidin`
(about 2.5 s) with a 6 s limit. With no hardening, 5/5 runs failed against a CPU hog at the same priority,
5/5 against one at priority 20 and 5/5 against a crash loop; at priority 40, 0/5 failed in every case. One of
five baseline runs also failed, probably the job's own load disturbing the canary at the same priority.

[`examples/ticker/ticker.c`](../examples/ticker/ticker.c) is a second program, a
single 100 Hz periodic task with a 5 ms deadline, about seventy lines long.
Siege tests it with no changes to the attackers. It is more fragile than the
reference pipeline, which shows that the result is specific to each program
(failed runs out of three; report in [`examples/ticker/`](../examples/ticker/)):

| Attack | Default priority | Ticker at priority 40 |
|---|---|---|
| CPU hog at the same priority | 3 / 3 | 0 / 3 |
| CPU hog at priority 20 | 3 / 3 | 0 / 3 |
| Crash loop at priority 20 | 3 / 3 | 0 / 3 |

The reference pipeline survived the crash loop, and the same-priority hog only
some of the time (see above). The ticker failed every time, because its deadline
is tighter and it has no slack.
