# Camera-ADAS isolation scenario

A front-camera driver-assistance stack has the same shape as Siege's reference
pipeline: a camera feeds a perception stage, which feeds a controller, and that
chain shares a computer with software that matters less (logging, a display,
connectivity). The question a system integrator has to answer is whether the
less important software can make the important chain miss its deadline. That
question is called *freedom from interference*, and it is what Siege measures.

This scenario pack reconfigures the reference pipeline to that setting and runs
it unchanged under the same attackers.

| | Reference config | ADAS config |
|---|---|---|
| Frame rate | 50 Hz | 30 Hz (`FRAME_MS=33`) |
| Deadline | 20 ms | 33 ms, one frame period |
| Pipeline | camera, detector, controller | the same |
| Other software | "attackers" | lower-criticality (QM) tasks sharing the machine |
| Files | `siege.json` | [`examples/adas/siege.json`](../examples/adas/siege.json) |

Run it with `./siege test --config examples/adas/siege.json`. The results,
report and JUnit file are in [`examples/adas/`](../examples/adas/).

## Result

9 scenarios, 4 profiles, 5 runs each, measured on QNX SDP 8.0 in QEMU. All 36
cases matched the expectation declared in the config.

| Interference channel | Scenario | No hardening | Priority | CPU affinity | CPU budget |
|---|---|---|---|---|---|
| Execution time | QM CPU load, same or lower priority | pass | pass | pass | pass |
| Execution time | QM CPU load above the pipeline (prio 20) | **fail 5/5** | pass | pass | pass |
| Execution time | QM perception neighbour above the pipeline | **fail 5/5** | pass | pass | pass |
| Shared service | QM client floods the shared detector (prio 30) | **fail 5/5** | pass | **fail 5/5** | **fail 5/5** |
| Memory | QM memory load | pass | pass | pass | pass |
| Process failure | QM service crash loop | pass | pass | pass | pass |
| Shared lock | lock shared with a QM task, default mutex | pass | pass | pass | pass |
| Fault recovery | detector killed, supervised restart | pass | pass | pass | pass |

"Pass" means at most 20% of runs failed; "fail 5/5" means all five did. The
full table with confidence intervals is in
[`examples/adas/report.md`](../examples/adas/report.md).

The result at 30 Hz is the same as at 50 Hz. Raising the pipeline's priority
above the other software fixed everything observed. A flood of a shared
service is the case where giving the pipeline its own CPU or capping the
other software's CPU did not help.

## How this maps to the usual safety vocabulary

ISO 26262 Part 6 discusses freedom from interference between software
elements of different criticality along three channels. This is my reading of
it, not an assessment by a safety assessor.

| Channel in the standard | What Siege exercises |
|---|---|
| Timing and execution | CPU hogs, expensive requests to a shared service, a lock held by a low-priority task |
| Memory | a memory-touching process; a process that exhausts descriptors and connections |
| Exchange of information | message floods to a shared server; a service that crashes and restarts |

Siege covers some of the timing and exchange channels, by experiment. It does
not cover memory protection faults (writes into another process's memory), which
QNX handles with separate address spaces and which are not tested here.

## What this does not show

* It is not a safety case, not an ISO 26262 assessment and not a certification
  claim. [`test-report.md`](test-report.md) is the same kind of evidence record.
* The pipeline is a stand-in with synthetic frames, not a perception stack.
* QNX OS for Safety, the certified product, is not in the free SDP and was not
  used. Everything here ran on QNX SDP 8.0 in QEMU, and no hardware was tested.
* No attack failing in 5 runs means it was not observed, not that it cannot happen.
