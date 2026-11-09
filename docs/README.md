# Documentation

Where to start depends on what you want. **If you read only two:** [`trace-evidence.md`](trace-evidence.md) (why a tiny attacker breaks the pipeline) and [`report.html`](report.html) (every result).

**To understand what Siege found**

| Document | What it is |
|---|---|
| [`report.html`](report.html) / [`report.md`](report.md) | The results: every attack against every hardening profile, with a per-run drill-down, charts, and an evidence table by interference channel |
| [`patterns.md`](patterns.md) | Each finding as a named pattern: symptom, cause, how Siege shows it, what fixes it and what does not |
| [`more-attackers.md`](more-attackers.md) | Memory-bandwidth, timer-storm and kernel-call attackers and what they did and did not show |
| [`name-squatting.md`](name-squatting.md) | A process that takes the detector's service name after a restart, why no CPU setting helps, and the owner check that does |
| [`why-qnx.md`](why-qnx.md) | Which findings depend on how QNX works and which would hold on any fixed-priority scheduler, with the history behind priority inversion |
| [`adas-isolation.md`](adas-isolation.md) | The same pipeline configured as a 30 Hz front-camera driver-assistance stack sharing a machine with lower-criticality software, and how the findings map to freedom-from-interference vocabulary |
| [`security-policy.md`](security-policy.md) | QNX security policies (connect denial, priority ceiling, name-attach denial) against the scheduling profiles, with the predictions made before the runs |
| [`mechanism-control.md`](mechanism-control.md) | The control experiment that removes the priority boost, with its validity check, and what it does and does not show |
| [`fortress.md`](fortress.md) | One configuration with every defence at once against all 26 scenarios: a clean replication, an earlier worse run, and the open question about why |
| [`trace-marks.md`](trace-marks.md) | The controller's own events written into the QNX kernel trace with `TraceEvent`, and who held the CPU before each stall |
| [`testing-your-program.md`](testing-your-program.md) | How to attack your own real-time program with Siege: the config, the output it must print, and two worked examples |
| [`docker.md`](docker.md) | The tools container, the experimental builder image, what the CI workflow checks, and why there is no Kubernetes |
| [`code-review.md`](code-review.md) | An independent read of the C programs: what was found, what was fixed, what was left and why, and what it means for the published numbers |
| [`integrator-checklist.md`](integrator-checklist.md) | Ten questions to ask when mixing software of different importance on one QNX machine, each tied to a Siege scenario and what we measured |
| [`for-teams.md`](for-teams.md) | How a team integrating mixed-criticality software on QNX would use Siege: the loop, which mechanism for which symptom, what to hand a reviewer, and where it stops |
| [`first-run-test.md`](first-run-test.md) | A ten-minute checklist for a first-time user, and what to send back |
| [`test-report.html`](test-report.html) / [`test-report.md`](test-report.md) | The same evidence as a safety-style test record: numbered test cases, pass criteria, traceability, limits, sign-off. Evidence, not certification |

**Experiments and negative results** (not needed to follow the main story)

| Document | What it is |
|---|---|
| [`predictor.md`](predictor.md), [`predictor-online.md`](predictor-online.md) | The from-scratch learned monitor: offline results held out by attacker, then scored on 500 fresh runs on QNX, where it did not beat a plain rule |
| [`search.md`](search.md) | `./siege search`: random attack combinations shrunk to minimal failing cases, and what it found |
| [`confidence-gate.md`](confidence-gate.md) | The detector's score-band gate: strong on the object it was calibrated on, flags everything when the object changes, and a margin signal that failed |

**To set it up and run it**

| Document | What it is |
|---|---|
| [`codelab-qnx-on-apple-silicon.md`](codelab-qnx-on-apple-silicon.md) | A codelab: QNX 8.0 on an Apple Silicon Mac for $0, from nothing to a booted image |
| [`../README.md`](../README.md) | The project overview, quick start, and how to test your own program |
| [`pc.md`](pc.md) | The x86-64 build: an image from `mkqnximage`, Siege installed over ssh, results, and what is untested for a real PC |
| [`hardware.md`](hardware.md) | Running Siege on a real QNX board, and how to share the result |
| [`mechanism-proof.md`](mechanism-proof.md) | The `workflood` mechanism observed directly: the detector's priority while it serves a higher-priority flood |
| [`landscape.md`](landscape.md) | The safe region: pipeline priority against attacker priority |
| [`trace-evidence.md`](trace-evidence.md) | A kernel trace of the flood: who actually used the CPU |

**Raw data and pictures**

* [`results/`](results/): every measured run as JSON
* [`architecture.svg`](architecture.svg), [`live-dashboard.gif`](live-dashboard.gif) (a real recorded run)
* [`../examples/`](../examples/): a second program (`ticker`), the trained-network
  validation (`cnn`), and a CI example
