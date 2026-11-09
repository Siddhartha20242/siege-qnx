# Mechanism proof: the server runs at its client's priority

QNX documents that a server runs at the priority of the client it is serving, and receives messages highest sender priority first.
This page shows the boost **occurring** (observed, not inferred). It does not show that the boost is what breaks the pipeline: the control experiment
([`mechanism-control.md`](mechanism-control.md)) removes it and the flood still fails. `pidin` sampled each process's priority 60 times (every 0.1 s) from a shell at priority 61,
once with no attacker and once with a client at priority 30 sending the detector expensive requests.
The detector, camera and controller are all configured at priority 10.

| Process | No attacker | Under the priority-30 flood |
|---|---|---|
| `detector` | priority 10: 43 of 43 samples | priority 10: 8 of 44 samples, priority 30: 36 of 44 samples |
| `frame_src` | priority 10: 43 of 43 samples | priority 10: 44 of 44 samples |
| `controller` | priority 10: 43 of 43 samples | priority 10: 9 of 44 samples, priority 30: 35 of 44 samples |
| `attacker` | priority 1: 114 of 171 samples, priority 60: 57 of 171 samples | priority 1: 118 of 298 samples, priority 30: 80 of 298 samples, priority 60: 100 of 298 samples |

The detector was at its configured priority 10 in every control sample. Under the flood it was seen above 10 in 36 of 44 samples. That is the inheritance, observed: nothing in the detector's code changes its priority; the kernel raises it to the client's while it serves that client's request.

**An observation we did not expect to find (but that is standard QNX behaviour, as a reviewer pointed out).** The controller was also seen above its configured priority (35 of 44 samples), although it only ever receives messages from the detector and never from the attacker. That is consistent with the boost travelling along the message chain, since the detector sends to the controller while it is itself running at the client's priority. We did not investigate it further, so treat that explanation as a hypothesis, not a result.

The camera (`frame_src`) only ever sends and never serves a request, so it is not boosted. The `attacker` row also includes its idle-priority helper threads (priority 1) and its main thread waiting at priority 60, which are not part of the finding.

Sampling is coarse: `pidin` reads a snapshot, so the share of samples at priority 30 is an estimate of the share of time the
detector spends boosted, not a bound on it.
