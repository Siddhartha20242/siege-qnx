# Documentation

Where to start depends on what you want.

**To understand what Siege found**

| Document | What it is |
|---|---|
| [`report.html`](report.html) / [`report.md`](report.md) | The results: every attack against every hardening profile, with a per-run drill-down, charts, and an evidence table by interference channel |
| [`patterns.md`](patterns.md) | Each finding as a named pattern: symptom, cause, how Siege shows it, what fixes it and what does not |
| [`why-qnx.md`](why-qnx.md) | Which findings depend on how QNX works and which would hold on any fixed-priority scheduler, with the history behind priority inversion |
| [`adas-isolation.md`](adas-isolation.md) | The same pipeline configured as a 30 Hz front-camera driver-assistance stack sharing a machine with lower-criticality software, and how the findings map to freedom-from-interference vocabulary |
| [`test-report.html`](test-report.html) / [`test-report.md`](test-report.md) | The same evidence as a safety-style test record: numbered test cases, pass criteria, traceability, limits, sign-off. Evidence, not certification |

**To set it up and run it**

| Document | What it is |
|---|---|
| [`codelab-qnx-on-apple-silicon.md`](codelab-qnx-on-apple-silicon.md) | A codelab: QNX 8.0 on an Apple Silicon Mac for $0, from nothing to a booted image |
| [`../README.md`](../README.md) | The project overview, quick start, and how to test your own program |
| [`hardware.md`](hardware.md) | Running Siege on a real QNX board, and how to share the result |
| [`mechanism-proof.md`](mechanism-proof.md) | The `workflood` mechanism observed directly: the detector's priority while it serves a higher-priority flood |
| [`landscape.md`](landscape.md) | The safe region: pipeline priority against attacker priority |
| [`trace-evidence.md`](trace-evidence.md) | A kernel trace of the flood: who actually used the CPU |

**Raw data and pictures**

* [`results/`](results/): every measured run as JSON
* [`architecture.svg`](architecture.svg), [`live-dashboard.gif`](live-dashboard.gif) (a real recorded run)
* [`../examples/`](../examples/): a second program (`ticker`), the trained-network
  validation (`cnn`), and a CI example
