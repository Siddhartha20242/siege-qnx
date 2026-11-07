# Predictor, scored online

500 fresh runs on QNX in QEMU with the predictor running inside the controller (thread priority above all other work), not used for training. An alarm is the first prediction at or above 0.5 using up to K seconds of evidence.

| Seconds of evidence | Network F1 | Recall | Precision | Rule F1 | Recall | Precision |
|---|---|---|---|---|---|---|
| 1 | 0.56 | 0.50 | 0.64 | 0.42 | 0.28 | 0.78 |
| 2 | 0.85 | 0.97 | 0.76 | 0.94 | 1.00 | 0.89 |
| 3 | 0.86 | 0.99 | 0.76 | 0.94 | 1.00 | 0.89 |

## When it warns

For failing runs that it flagged, the alarm came a median of 3.5 s before the end of a 5 s run (earliest 3.5 s, latest 1.5 s). The verdict itself comes only at the end of the run.

## Pattern named at the alarm (failing runs that were flagged)

| True pattern | Runs | Named correctly | Most common wrong answer |
|---|---|---|---|
| CPU starvation | 46 | 28 | dead service |
| shared-service queue | 15 | 10 | CPU starvation |
| lock inversion | 20 | 19 | dead service |
| dead service | 20 | 20 | - |

## An attacker the network has never seen: name squatting

40 runs (18 failed). Network: 18 caught, 0 missed, 2 false alarms. Rule: 18 caught, 0 missed, 0 false alarms.

## False alarms

32 of 398 passing runs raised an alarm.
Most: kill detector, supervised (17), name squat, race after restart (2), cpu hog   @prio 20 (2), AI neighbour@prio 10 (2).

## Limits

* Fresh runs, but of the same scenarios the network was trained on, apart from name squatting. This tests repeatability, not breadth.
* QEMU emulation, one image, one 20 ms deadline.
* The network only reads latency; a pass or fail it predicts is the controller's verdict, not a diagnosis of cause.
