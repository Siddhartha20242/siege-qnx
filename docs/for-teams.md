# Using Siege on a team's own system

This page is for someone who integrates software of different importance on one
QNX machine, for example a camera pipeline next to an infotainment or analytics
process, and has to answer "what happens to the pipeline when its neighbour
misbehaves?" with something better than "it should be fine".

Siege gives you a repeatable way to ask that question, a place to write the
answer down, and a build step that fails when the answer changes. It produces
evidence for a review. It does not certify anything.

## The loop

1. **Describe your pipeline once.** `./siege init mypipe --command "mypipe -d {dur}"`
   writes a config. Your program prints one summary line and one `RESULT PASS|FAIL`
   line; [Testing your own program](../README.md#testing-your-own-program) has the
   details. `./siege calibrate` measures the clean noise floor and suggests a deadline.
2. **Measure the clean system first.** `./siege test --profile none --json none.json`.
   A pipeline that fails its own baseline cannot be hardened by attack results.
3. **Attack it.** The scenarios in `siege.json` are data: CPU hogs above and at your
   priority, an AI-style compute neighbour, a message flood, a flood of a shared service,
   memory bandwidth, a kill, a name squat. Add the neighbour you actually worry about.
4. **Replay under each mechanism you could ship**, one profile at a time, and read the
   table: `./siege show` for a quick look, `./siege report` for intervals and charts.
5. **Write down what you expect.** Each scenario can declare its expected outcome per
   profile. This is the step that turns a one-off experiment into a regression test.
6. **Gate on it.** `./siege ci` writes JUnit XML and exits non-zero if any case differs
   from its expectation. A regression and an unexpected fix both fail the build, so a
   person looks. See [`examples/ci/github-actions.yml`](../examples/ci/github-actions.yml).

## Which mechanism for which symptom

| What you see | Likely cause | What helped in our runs | What did not |
|---|---|---|---|
| Pipeline starves when a neighbour spins | Neighbour at or above your priority | `prio`, `isolate`, `budget`, or a policy ceiling below your priority | n/a |
| Latency spikes with a neighbour using almost no CPU | A shared server running at the client's priority | Raise the pipeline's priority; or a policy that denies the neighbour the connection | `isolate`, `budget` |
| A stage dies and nothing replaces it | No supervisor | A supervisor | any scheduling setting |
| Service restarts but the pipeline stays broken | Another process took the service name | Owner check in the supervisor; or deny the neighbour name registration | any scheduling setting |
| Missed deadlines when a low-priority holder owns a lock | Priority inversion | A priority-inheriting mutex (QNX's default is one) | every profile and every policy |

Each row is measured, in emulation, in [`patterns.md`](patterns.md), the
[main report](report.md) and [`security-policy.md`](security-policy.md).

## What to hand a reviewer

* [`test-report.html`](test-report.html), the same evidence as numbered test cases with
  pass criteria and traceability, and the sections that say what it does not cover.
* [`adas-isolation.md`](adas-isolation.md), which maps the findings to
  freedom-from-interference vocabulary without claiming a standard is met.
* The raw per-run JSON, so a sceptic can recompute any cell.

## Where it stops

* The timing so far is from QEMU. Before relying on a number, run the same matrix on your
  target ([`hardware.md`](hardware.md)) and keep hardware and emulator results separate.
* It tests the attacks you wrote. A table of passes means those attacks did not break it.
* Passing runs are not a safety argument. They are one input to one.
