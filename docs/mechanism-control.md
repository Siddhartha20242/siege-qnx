# Control experiment: what happens if the server stops taking its client's priority?

The headline failure (`workflood` at priority 30) has two candidate causes that the first measurements could not separate:
the **priority boost** (while it serves a request the detector runs at its client's priority) and the **queue order and serial
service** of a single-threaded server (requests from priority 30 are delivered first, and each costs real CPU).

## The experiment
`DET_FIXED_PRIO=1` creates the detector's channel with `_NTO_CHF_FIXED_PRIORITY` (`pipeline/detector.c`: `ChannelCreate`,
`dispatch_create_channel`, `name_attach` on that channel). The receiving thread then keeps the detector's own priority instead of
taking the sender's; messages are still queued by sender priority. The prediction was written into
[`examples/control/siege.json`](../examples/control/siege.json) before the run: **the flood still fails**, because queue order and
serial service, not the boost, do the damage.

**The flag does what it claims.** `pidin` sampled the detector's priority 30 times during a priority-30 flood
([`results/fixed-prio-check.json`](results/fixed-prio-check.json)): without the flag it was at **30 in 30 of 30** samples, with
the flag at **10 in 30 of 30**.

## Result (QEMU, 10 runs per cell; the 30-run repeat is pending, so this is provisional)

| `workflood` at priority 30 | Normal detector | Detector that keeps its own priority |
|---|---|---|
| Profile `none` (everything at 10) | failed 10/10, longest silence about 600 ms | failed 10/10, **silent for the whole run (abandoned in all 10)** |
| Profile `prio` (pipeline at 40) | failed 1/10 | failed 1/10 |

Raw data: [`examples/control/results/`](../examples/control/results/).

## What this does and does not show
- **Shown (provisionally):** removing the boost does not remove the failure, so the boost is **not necessary** for it. The prediction held.
- **Not shown:** that the boost contributes nothing. Removing it also changes other things, for example the detector now runs at priority 10
  under round-robin and the boost no longer passes on to the controller.
- **Unexplained:** the failure changed shape. With the normal detector the pipeline keeps delivering frames with gaps of about 600 ms;
  without the boost it delivers none (no per-second summaries at all, abandoned after 3 s). We do not know why. Do not put the
  mechanism in a headline until this is understood.
- **What the control does not test:** a multi-threaded detector, per-client limits, or a queue that is not ordered by sender priority.
  A QNX architect would reach for server-side fixes like those before reshuffling priorities.
