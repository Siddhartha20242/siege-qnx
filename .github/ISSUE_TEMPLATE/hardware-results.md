---
name: Hardware results
about: Share results from running Siege on a real QNX board (see docs/hardware.md)
title: "Hardware results: "
labels: hardware
---

**Board and QNX version**

**Commands you ran** (profiles, `--runs`, any `--only` filters)

**Results**: attach the `hw-*.json` files, or paste `hw-report.md`.

**Did the headline findings reproduce?**
1. CPU hog at priority 20 starves the unhardened pipeline:
2. `workflood` is fixed only by the `prio` profile:
3. AI neighbour at priority 20 fails unhardened, passes hardened:
4. A killed detector needs the supervisor:

**Anything that failed to run** (command and output)
