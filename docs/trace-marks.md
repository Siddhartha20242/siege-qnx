# The controller's own events in the kernel trace

With `SIEGE_TRACE=1` the controller calls `TraceEvent(_NTO_TRACE_INSERTUSRSTREVENT, ...)` each time it records a stall, an outage or a late frame (`pipeline/controller.c`, `trace_mark`). The same one-second trace as [`trace-evidence.md`](trace-evidence.md) (a fresh run, so the shares differ slightly) holds 10 of them: 10 stall. `traceprinter` prints them as `USREVENT :EVENT:1 STR:"stall 10 1013"`, next to the scheduling events, so a missed deadline can be read against what the CPUs were doing.

In the 100 ms before each of the 10 events, the CPUs (all 2) were running:

| Process | Share of CPU time before a stall or outage |
|---|---|
| `detector` | 49.7% |
| `idle and kernel (procnto)` | 49.4% |
| `attacker` | 0.5% |
| `frame_src` | 0.2% |
| `tracelogger` | 0.2% |
| `controller` | 0.0% |
| `slogger2` | 0.0% |

Around every stall the detector, not the attacker, is the one using the CPU: the attacker stays under a few percent while the detector holds about one of the two CPUs. That ties each missed deadline to the same cause the CPU-share table shows, event by event.

Limits: one run and a one-second window, so a handful of events; shares come from thread-running events and ignore interrupt time; the printed events carry no priorities.
