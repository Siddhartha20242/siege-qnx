# A confidence gate on the detector: what it does and where it stops

The detector is a small convolutional network. Its output score (the peak of its output map) tells us something about
whether its answer can be trusted. This page records what we measured, including the parts that did not work.

## The score-band gate

The true object has a known brightness, so the network's peak score for it falls in a narrow band. The band is calibrated
**only on the synthetic camera** (noise background, a 5x5 object at brightness 200) and then applied unchanged to
held-out real-photo crops (`tools/eval_confidence.py`, raw data in
[`results/confidence.json`](results/confidence.json)).

| | Result |
|---|---|
| Band, from 3,000 synthetic frames | 37.58 to 41.53 |
| Offline, 7,000 photo crops (two photos, object 5x5 at 200) | flags 486 of 554 wrong answers and 0 of 6,446 right ones; accuracy of accepted answers 92.1% to 99.0% |
| On the QNX image (the controller's `GATE` line, hard photo scene) | all 78 wrong answers flagged in each of 6 runs; 0 right ones flagged; 0 wrong answers passed (the input is deterministic, so the six runs are one sample repeated, not six independent results) ([`results/gate-on-qnx.json`](results/gate-on-qnx.json)) |

So **for the object it was calibrated on**, the gate is a strong detector of "this answer should not be trusted".

## Where it stops

The gate is narrow ([`results/confidence-robustness.json`](results/confidence-robustness.json), 150 crops per photo per setting):

- Change the object's brightness (150, 175, 225 or 250 instead of 200), or its size to 3x3, and the gate flags **every**
  correct answer too, because their scores fall outside the band. At the calibrated object (200, 5x5 or 7x7) it keeps all
  of them.
- Even at the calibrated object, a few wrong answers get through on the brightest backgrounds (2 to 7 per 300 crops).
- It was tested on two photographs and one object type.

So it is a **calibration-consistency check**: it tells you the detector is producing what it produced when it was
validated. It is not a general uncertainty estimate. Flagging every answer when the object changes is the safe direction
for a safety function, but it is not discrimination, and a deployment would have to calibrate the band per object.

## A better signal that did not work

We tried gating on the ratio of the strongest competing peak to the best peak, which should not depend on the object's
brightness (`tools/eval_margin.py`). Calibrated on the synthetic camera, it rejects almost every correct answer on photo
backgrounds (for example 233 of 300 at the standard object), because real textures create strong competing peaks. We do
not use it.

## What the controller does with it

`SCORE_BAND=lo:hi` makes the controller **count** detections outside the band (`GATE flagged_wrong=... flagged_right=...
silent_wrong=...`). It never changes the verdict.

It also runs an **advisory safe state** (`SAFE_WIN`, `SAFE_K`; default: at least 3 unsure among the last 8 detections enters it,
none among the last 8 leaves it), printed as `SAFE enter` / `SAFE clear` lines and written to the kernel trace. Its measurement ([`results/safe-state.json`](results/safe-state.json); the expectation, written first, was no entries on the first two inputs and entries on the hard scene):

| Input (8 runs each) | Wrong answers | Flagged wrong | Flagged right | Wrong, not flagged | Safe-state entries | Mean ms from first unsure to safe |
|---|---|---|---|---|---|---|
| synthetic camera | 0 of 3199 | 0 | 0 | 0 | 0 (in 0 of 8 runs) | - |
| real-photo scene (cap 140) | 0 of 3198 | 0 | 0 | 0 | 0 (in 0 of 8 runs) | - |
| hard scene (cap 255) | 624 of 3200 | 624 | 0 | 0 | 104 (in 8 of 8 runs) | [179, 183] |

The inputs are deterministic, so the eight runs are not independent samples. The time to safe is set mostly by the window rule (3 unsure of the last 8) and the frame period, not by the detector. **A limit that matters:** it is evaluated only when a detection arrives, so a
detector that goes silent can never trigger it. The silent case is the one a safety function most needs to catch, and it is
covered only by the controller's separate stall and abandon logic, not by this gate.
