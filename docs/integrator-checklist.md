# An interference checklist for QNX integrators

**Read this first.** These questions come from one synthetic reference pipeline, a single-threaded detector fed by a synthetic camera,
run in QEMU. They are things to **check on your own system**, not results about it. Siege does not cover interrupt load,
camera, GPU or display drivers, DMA bandwidth, a hypervisor, memory-protection faults, or hardware timing, and there is no
certification mapping. In real integrations those are often where the interference comes from. The data below are small samples
(5 to 15 runs per cell), so read "failed 0 of 15" as "not observed in 15 runs", not "passes".

| # | Question to check on your system | Siege scenario (`./siege test --only "..."`) | What we saw (QEMU, toy pipeline) |
|---|---|---|---|
| 1 | Can anything less important run at or above your pipeline's priority? | `cpu hog   @prio 20`, `cpu hog   @prio 10` | Above the pipeline it starved it; at the same priority it failed about half the runs |
| 2 | Does a shared server serve clients of lower importance, and what protects the high-importance client? Server-side options to consider first: a thread pool, per-client limits keyed on client identity, a channel that keeps its own priority, or not sharing the server with untrusted clients. | `workflood @prio 30` | A neighbour that spent about 0.4% CPU itself made the single-threaded detector spend a whole CPU. Raising the pipeline's priority or denying the connection by policy fixed it; giving the pipeline its own CPU or demoting the neighbour after a CPU budget did not. This is a known design hazard of a shared single-threaded server; the 15/15 figure depends on a priority we chose for the neighbour |
| 3 | Do you share a lock across importance levels, and is it priority-inheriting? | `priority inversion (plain mutex)` vs `(inheriting mutex)` | A mutex made with `PTHREAD_PRIO_NONE` failed under every setting (a fixture built to fail). Use `PTHREAD_PRIO_INHERIT` and test it on yours. Semaphores and hand-made locks do not inherit priority, and process-shared mutexes should be robust |
| 4 | Can a stage die and nothing replace it, and how long does recovery take? | `kill detector, no supervisor` vs `supervised` | Without a supervisor it never recovered; with one the restart took a few milliseconds |
| 5 | Can another process take your service name after a restart? | `name squat, race after restart` | It broke the pipeline under every scheduling setting; the supervisor's owner check or a policy denying name registration fixed it. The owner check in our supervisor passes if it cannot read the owner (it fails open), so do not copy it as is |
| 6 | Does each process hold only the abilities it needs? | `tools/minimize_policy.py` on your process, and QNX's own policy-generation tools | For our toy detector, 58 of 63 abilities were unneeded and a type with none ran it. Removing one ability at a time over the code paths you happened to run is not least privilege; start from deny-by-default. The number is specific to ours |
| 7 | If you use a priority ceiling, is it strictly below the process you protect? | `secpol-ceiling` | A ceiling equal to the pipeline's priority still failed (one line to remember, not a finding about your system) |
| 8 | Do receivers validate message length and check who sent each message, and does something decide who may connect? | `forge: ...` scenarios ([`forged-messages.md`](forged-messages.md)) | Length checks are in the pipeline. Our pipeline does not check the sender, although QNX gives a server the sender's identity (`_msg_info`, `ConnectClientInfo`) which the client cannot forge; a policy can also deny the connection |
| 9 | Will you notice if it regresses? | `./siege ci` | The attack gate needs a QNX runner you set up; the repository's own CI only checks saved data. The example attack-gate workflow has never been run on a real runner |

Two earlier rows (CPU affinity or a CPU budget as protection for a shared server) are folded into row 2.

## How to use it
1. Pick the rows that match your architecture and run them against your own build (`./siege init`, [`testing-your-program.md`](testing-your-program.md)).
2. Write the outcome you expect before each run.
3. Treat a surprise as a finding, not a failure of the test.

## What a one-week trial would answer
Whether the method finds something you did not know, and how many engineer-days it takes to adapt to your pipeline. It cannot
tell you whether your board meets its deadlines.
