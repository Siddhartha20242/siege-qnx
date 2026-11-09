#!/usr/bin/env python3
"""Does the detector know when it is wrong? Test whether its own score can flag its errors.

    python3 tools/eval_confidence.py        # needs numpy, Pillow and scikit-learn, like eval_real_images.py

A safety function that only works when the AI is right is not much use. The useful pairing is an AI that can say
"I am not sure", so a supervisor can fall back to a safe action. The detector already produces a score (the peak
of its output map). The true object has a known brightness, so its score falls in a narrow band; a score outside
that band means something other than the object is driving the answer. The band is calibrated ONLY on the synthetic
camera frames the system was built for (noise background, object at 200), then applied unchanged to held-out
real-photo crops (the same ones as eval_real_images.py). Writes docs/results/confidence.json.
"""
import json, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eval_real_images as E

ROOT = E.ROOT


def collect(max_bg, n_per_photo, rng, wts):
    """(correct, score) for every crop."""
    out = []
    for _, im in E.photos():
        h, w = im.shape
        im = im / im.max() * max_bg
        x0 = int(w * 0.7)
        for _ in range(n_per_photo):
            cx = rng.integers(x0, w - E.W)
            cy = rng.integers(0, h - E.W)
            frame = im[cy:cy + E.W, cx:cx + E.W].copy()
            bx, by = rng.integers(4, 28, size=2)
            frame[by - 2:by + 3, bx - 2:bx + 3] = 200
            x = (np.clip(frame, 0, 255).astype(np.float32) / 255.0)[None]
            x = np.maximum(E.conv(x, wts["cnn_w1"], wts["cnn_b1"], 3), 0)
            x = np.maximum(E.conv(x, wts["cnn_w2"], wts["cnn_b2"], 3), 0)
            s = E.conv(x, wts["cnn_w3"], wts["cnn_b3"], 1)[0]
            i = int(s.argmax())
            px, py = (i % 28) + 2, (i // 28) + 2
            out.append((abs(px - bx) <= 1 and abs(py - by) <= 1, float(s.max())))
    return out


def synthetic_band(wts, rng, n=3000, margin=0.05):
    """Score range of correct detections on the synthetic camera: noise 0..15, object 200 (pipeline/frame_src.c)."""
    ok = []
    for _ in range(n):
        frame = rng.integers(0, 16, size=(E.W, E.W)).astype(np.float32)
        bx, by = rng.integers(4, 28, size=2)
        frame[by - 2:by + 3, bx - 2:bx + 3] = 200
        x = (frame / 255.0)[None]
        x = np.maximum(E.conv(x, wts["cnn_w1"], wts["cnn_b1"], 3), 0)
        x = np.maximum(E.conv(x, wts["cnn_w2"], wts["cnn_b2"], 3), 0)
        s = E.conv(x, wts["cnn_w3"], wts["cnn_b3"], 1)[0]
        i = int(s.argmax())
        if abs((i % 28) + 2 - bx) <= 1 and abs((i // 28) + 2 - by) <= 1:
            ok.append(float(s.max()))
    lo, hi = min(ok), max(ok)
    span = hi - lo
    return lo - margin * max(span, abs(hi)), hi + margin * max(span, abs(hi)), len(ok), n


def main():
    wts = E.load_weights()
    rng = np.random.default_rng(20261108)
    lo, hi, n_ok, n_cal = synthetic_band(wts, np.random.default_rng(7), 3000)
    rows, tot = [], dict(right_acc=0, right_rej=0, wrong_acc=0, wrong_rej=0)
    for cap in (60, 100, 140, 180, 200, 220, 255):
        d = collect(cap, 500, rng, wts)
        r = dict(max_background=cap, crops=len(d), accuracy=round(sum(a for a, _ in d) / len(d), 4))
        ra = sum(1 for a, sc in d if a and lo <= sc <= hi); rr = sum(1 for a, sc in d if a and not lo <= sc <= hi)
        wa = sum(1 for a, sc in d if not a and lo <= sc <= hi); wr = sum(1 for a, sc in d if not a and not lo <= sc <= hi)
        r.update(right_accepted=ra, right_rejected=rr, wrong_accepted=wa, wrong_rejected=wr,
                 accuracy_of_accepted=round(ra / (ra + wa), 4) if ra + wa else None)
        rows.append(r)
        for k, v in zip(tot, (ra, rr, wa, wr)):
            tot[k] += v
    pooled = dict(tot, accuracy_before=round((tot["right_acc"] + tot["right_rej"]) / (sum(tot.values())), 4),
                  accuracy_of_accepted=round(tot["right_acc"] / (tot["right_acc"] + tot["wrong_acc"]), 4))
    out = {"calibration": {"frames": n_cal, "correct": n_ok, "band": [round(lo, 3), round(hi, 3)]},
           "per_brightness": rows, "pooled": pooled,
           "note": "band calibrated on synthetic frames only, applied unchanged to held-out real-photo crops (right-hand 30% of two CC BY 2.0 photos; object level 200)"}
    json.dump(out, open(os.path.join(ROOT, "docs", "results", "confidence.json"), "w"), indent=1)
    print(f"band [{lo:.2f}, {hi:.2f}] from {n_ok}/{n_cal} correct synthetic detections")
    print(f"{'background cap':>15} {'accuracy':>9} {'right kept':>11} {'right dropped':>14} {'wrong kept':>11} {'wrong dropped':>14}")
    for r in rows:
        print(f"{r['max_background']:>15} {r['accuracy']:>9.3f} {r['right_accepted']:>11} {r['right_rejected']:>14} {r['wrong_accepted']:>11} {r['wrong_rejected']:>14}")
    print(f"pooled: {pooled}")


def collect_obj(max_bg, n_per_photo, rng, wts, level, size):
    """Like collect(), but with the object's brightness and size changed. The detector was built for a 5x5 object at 200."""
    out = []
    half = size // 2
    for _, im in E.photos():
        h, w = im.shape
        im = im / im.max() * max_bg
        x0 = int(w * 0.7)
        for _ in range(n_per_photo):
            cx = rng.integers(x0, w - E.W); cy = rng.integers(0, h - E.W)
            frame = im[cy:cy + E.W, cx:cx + E.W].copy()
            bx, by = rng.integers(4, 28, size=2)
            frame[by - half:by + half + 1, bx - half:bx + half + 1] = level
            x = (np.clip(frame, 0, 255).astype(np.float32) / 255.0)[None]
            x = np.maximum(E.conv(x, wts["cnn_w1"], wts["cnn_b1"], 3), 0)
            x = np.maximum(E.conv(x, wts["cnn_w2"], wts["cnn_b2"], 3), 0)
            s = E.conv(x, wts["cnn_w3"], wts["cnn_b3"], 1)[0]
            i = int(s.argmax())
            out.append((abs((i % 28) + 2 - bx) <= 1 and abs((i // 28) + 2 - by) <= 1, float(s.max())))
    return out


def robustness():
    """What happens to the gate when the object is not the one it was calibrated on?"""
    wts = E.load_weights()
    lo, hi, _, _ = synthetic_band(wts, np.random.default_rng(7), 3000)
    rng = np.random.default_rng(20261110)
    rows = []
    print(f"band [{lo:.2f}, {hi:.2f}] (calibrated on a 5x5 object at 200)")
    print(f"{'level':>6} {'size':>5} {'bg cap':>7} {'accuracy':>9} {'right kept':>11} {'right dropped':>14} {'wrong kept':>11} {'wrong dropped':>14}")
    for level in (150, 175, 200, 225, 250):
        for size in (3, 5, 7):
            for cap in (140, 255):
                d = collect_obj(cap, 150, rng, wts, level, size)
                ra = sum(1 for a, sc in d if a and lo <= sc <= hi); rr = sum(1 for a, sc in d if a and not lo <= sc <= hi)
                wa = sum(1 for a, sc in d if not a and lo <= sc <= hi); wr = sum(1 for a, sc in d if not a and not lo <= sc <= hi)
                rows.append(dict(object_level=level, object_size=size, max_background=cap, crops=len(d),
                                 accuracy=round(sum(a for a, _ in d) / len(d), 3), right_accepted=ra, right_rejected=rr,
                                 wrong_accepted=wa, wrong_rejected=wr))
                print(f"{level:>6} {size:>5} {cap:>7} {rows[-1]['accuracy']:>9.3f} {ra:>11} {rr:>14} {wa:>11} {wr:>14}")
    json.dump(dict(band=[round(lo, 3), round(hi, 3)], rows=rows,
                   note="band calibrated on a 5x5 object at 200 over noise; applied unchanged to other objects; photos are the two held-out crops sets"),
              open(os.path.join(ROOT, "docs", "results", "confidence-robustness.json"), "w"), indent=1)


if __name__ == "__main__":
    if "--robustness" in sys.argv:
        robustness()
    else:
        main()
