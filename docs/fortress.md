# `fortress`: every defence at once

The other profiles test one mechanism at a time. `fortress` combines them: the pipeline at
priority 40, the `lockdown` security policy (the detector, camera and controller each in a type with no abilities; attackers
capped at priority 9 and denied the detector's channel and service names), a supervisor for the detector, and the
supervisor's owner check on the service name (`image/pipeline.sh`, `PROFILE=fortress`).

The question: **does one configuration survive all 26 scenarios?** The expected outcome for each scenario was written into
[`examples/fortress/siege.json`](../examples/fortress/siege.json) before the first run: pass for 25, fail for the plain
mutex (a lock with no priority inheritance, which no setting fixes).

## Results (QEMU, 10 runs per scenario)

| | First run | Clean re-run |
|---|---|---|
| Runs with no parsable output | 10 of 260 | **0 of 260** |
| Failed runs excluding the plain-mutex scenario | 24 of 250 | **3 of 250** |
| Cases matching the pre-declared expectation (more than 2 of 10 failing counts as a fail) | not computed on the first run | **26 of 26** |

The plain mutex failed 10/10 in the re-run, as predicted. The three other failed runs were one each in `cpu hog @prio 10`,
`kill detector, no supervisor` (here the supervisor restarts the detector anyway) and `name squat, detector alive`: single
failures at about the rate seen with no attacker at all (1 in 30). Raw data:
[`fortress.json`](../examples/fortress/results/fortress.json) (first run), [`fortress-rerun.json`](../examples/fortress/results/fortress-rerun.json).

## What is not explained

**The first run was materially worse, and I do not know why.** Ten runs produced no parsable output, and beyond those there
were 24 unexpected failures against 3 in the re-run. The unparsed runs are counted as failures here, as they should be.

- The symptom did not reproduce in 114 further runs under `fortress` before the clean re-run, nor in the 260-run re-run.
- **Hypothesis, not tested yet:** the first run overlapped with other work on the same Mac (builds, test suites and other tools
  running at the same time), and QEMU's software emulation is sensitive to host load. A test that saturates the host's cores
  during a `fortress` run would show whether that reproduces it. It is queued.
- Until that test is done, this page's claim is limited to: **one clean 260-run replication of `fortress` met all 26
  expectations in QEMU; an earlier run under unknown conditions did not, and its cause is unexplained.**

The harness now keeps the raw end of the output of any unparsed run, so a recurrence can be diagnosed.

## What this does and does not show
It shows one combination of the QNX mechanisms studied here survived the attacks tried, in emulation. It does not show hardware
behaviour, other attacks, or a boot-time immutable policy (the policy is loaded at run time).

## Not a deployment policy
The `atk_t` type in these policies is restricted only in the three ways tested (connect, priority ceiling, name registration). It keeps most
other abilities (including ones for hardware access, signalling and debugging other processes), and the shell and harness type holds all of
them. So "denied the detector's channel" is true of that attacker type in this test, not of an untrusted process in general.
`tools/gen_secpol.py` lists exactly what each type holds.
