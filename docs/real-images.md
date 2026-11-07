# Real photographs as camera input

The camera in Siege is synthetic on purpose: it is deterministic, so every run
sees identical input. The fair follow-up question is whether the detector's
answers, and the isolation findings, depend on that. This page checks it with
real photographs. It is a robustness check on one easy task, not a new vision
benchmark.

## Data and licence

Two photographs, `china.jpg` and `flower.jpg`, that ship with scikit-learn as
sample images. Both are Creative Commons BY 2.0 (Flickr users danielbuechele
and vultilion; see the `README.txt` next to them in the scikit-learn package).
Nothing is downloaded: [`tools/make_scene.py`](../tools/make_scene.py) reads the
installed copies and writes 16 greyscale 32x32 crops to `pipeline/scene.h`
(about 50 KB), with the attribution in the file header. Crops come only from the
right-hand 30% of each photo, and the detector's weights were trained before
these photos were looked at, on synthetic frames only.

The 5x5 object (brightness 200) is drawn over each crop, as it is over noise.
The photo is scaled so its brightest pixel is 140, so the object stays the
brightest thing in the frame.

## 1. Does the detector still find the object?

[`tools/eval_real_images.py`](../tools/eval_real_images.py) runs the shipped
weights (a numpy copy of the C forward pass) on 1000 held-out crops per row:

| Brightest photo pixel (object = 200) | Exact | Within 1 px |
|---|---|---|
| 60 – 200 | 100% | 100% |
| 220 | 76% | 76% |
| 255 | 68% | 68% |

So the network handles a natural-image background as long as the object is the
brightest thing in the frame, and fails once the background outshines it. That
is what a bright-blob detector should do, and it is the honest limit of the
task: a 5x5 bright square is easy. Raw numbers: `docs/results/real-images.json`.

## 2. Do the isolation findings change?

`SCENE=1` makes `frame_src` use the photo crops (`frame_src -s`). With the CNN
detector and photo input, in QEMU, 5 runs each
([`examples/scene/`](../examples/scene/)):

| Scenario | no profile | `prio` |
|---|---|---|
| baseline | 0/5 fail | 0/5 fail |
| CPU hog at priority 20 | 5/5 fail | 0/5 fail |

Same pattern as with the noise input. Across these runs the controller checked
3,999 detections against ground truth and none was wrong (1,499 with no
profile, where the starved hog runs deliver fewer frames, and 2,500 under `prio`).

Reproduce:

```sh
./siege build
./siege test --config examples/scene/siege.json --profile none --json none.json
```

## What this does not show

* Five runs per cell and two scenarios, not the full matrix. It checks that the
  headline pattern survives, not every cell.
* The crops are 16 fixed patches that repeat, not a video. The detector is not
  tested on moving natural scenes, other object shapes or cameras.
* QEMU timing, not hardware.
