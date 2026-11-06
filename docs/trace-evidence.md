# What the kernel trace shows: who used the CPU

A kernel trace of 1 s taken 2 s into a run of the priority-30 `workflood` attack against the pipeline (no hardening, `IDLE_POLL=0`), 171 KB, 9939 printed events on 2 CPUs. The table attributes each CPU's time to the process named by its latest thread-running event.

Observed: 2.00 CPU-seconds in total.

| Process | Share of CPU time |
|---|---|
| `detector` | 49.8% |
| `idle and kernel (procnto)` | 49.5% |
| `attacker` | 0.4% |
| `frame_src` | 0.2% |
| `tracelogger` | 0.1% |
| `controller` | 0.0% |
| `slogger2` | 0.0% |

The attacker used 0.4% of the CPU time and the detector 49.8%. This supports the claim that the flooding attacker barely uses any CPU of its own: the damage is done through the detector's message queue.

The trace also contains the message traffic: 375 sends, 323 receives and 321 replies in the window.

Limits: a one-second window of one run; shares are from event timestamps and ignore time spent in interrupts; the printed events carry no priorities, so this trace does not show the priority inheritance itself (see `mechanism-proof.md`).
