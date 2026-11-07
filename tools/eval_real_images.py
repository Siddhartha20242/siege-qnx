#!/usr/bin/env python3
"""Check the shipped detector on real photographs instead of synthetic noise.

    python3 tools/eval_real_images.py            # needs numpy, Pillow and scikit-learn (for its two sample photos)

The camera in Siege is synthetic on purpose. This script asks the obvious
follow-up: does the detector's answer survive a natural-image background? It
takes 32x32 greyscale crops from two Creative Commons photographs bundled with
scikit-learn (china.jpg and flower.jpg, CC BY 2.0, see the README.txt in that
folder), pastes the same bright 5x5 object on them, and runs the detector
exactly as pipeline/detector.c does, using the weights in pipeline/model.h.

Crops come from the right-hand 30% of each photo only, so that if the weights
were ever retrained on photo crops from the left, this check would stay held out.
The photo is scaled so its brightest pixel is MAX_BG (the object is 200).
Prints a small table and writes docs/results/real-images.json.
"""
import json, os, re, sys
import numpy as np

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
W = 32


def load_weights():
    text = open(os.path.join(ROOT, "pipeline", "model.h")).read()
    out = {}
    for name, body in re.findall(r"static const float (\w+)\[\d+\] = \{([^}]*)\}", text):
        out[name] = np.array([float(v.strip().rstrip("f")) for v in body.replace("\n", " ").split(",") if v.strip()],
                             dtype=np.float32)
    return out


def conv(x, w, b, k):
    """Valid convolution, x [cin,H,W], w [cout,cin,k,k] flat."""
    cin, h, wd = x.shape
    cout = b.size
    w = w.reshape(cout, cin, k, k)
    oh, ow = h - k + 1, wd - k + 1
    y = np.zeros((cout, oh, ow), dtype=np.float32)
    for dy in range(k):
        for dx in range(k):
            y += np.einsum("oi,ihw->ohw", w[:, :, dy, dx], x[:, dy:dy + oh, dx:dx + ow])
    return y + b[:, None, None]


def detect(wts, frame):
    x = (frame.astype(np.float32) / 255.0)[None]
    x = np.maximum(conv(x, wts["cnn_w1"], wts["cnn_b1"], 3), 0)
    x = np.maximum(conv(x, wts["cnn_w2"], wts["cnn_b2"], 3), 0)
    s = conv(x, wts["cnn_w3"], wts["cnn_b3"], 1)[0]
    i = int(s.argmax())
    return (i % 28) + 2, (i // 28) + 2


def photos():
    from PIL import Image
    import sklearn.datasets as d
    folder = os.path.join(os.path.dirname(d.__file__), "images")
    for name in ("china.jpg", "flower.jpg"):
        im = np.asarray(Image.open(os.path.join(folder, name)).convert("L"), dtype=np.float32)
        yield name, im


def run(max_bg, n_per_photo, rng, wts):
    ok = within1 = total = 0
    for _, im in photos():
        h, w = im.shape
        im = im / im.max() * max_bg
        x0 = int(w * 0.7)
        for _ in range(n_per_photo):
            cx = rng.integers(x0, w - W)
            cy = rng.integers(0, h - W)
            frame = im[cy:cy + W, cx:cx + W].copy()
            bx, by = rng.integers(4, 28, size=2)
            frame[by - 2:by + 3, bx - 2:bx + 3] = 200
            px, py = detect(wts, np.clip(frame, 0, 255))
            total += 1
            ok += (px, py) == (bx, by)
            within1 += abs(px - bx) <= 1 and abs(py - by) <= 1
    return ok / total, within1 / total, total


def main():
    try:
        wts = load_weights()
        next(photos())
    except ImportError as e:
        sys.exit(f"missing module: {e}. pip install numpy pillow scikit-learn")
    rng = np.random.default_rng(20261107)
    rows = []
    print(f"{'photo brightness cap':>22} {'exact':>8} {'within 1 px':>12} {'crops':>7}")
    for cap in (60, 100, 140, 180, 200, 220, 255):
        e, w1, n = run(cap, 500, rng, wts)
        rows.append({"max_background": cap, "exact": round(e, 4), "within1": round(w1, 4), "crops": n})
        print(f"{cap:>22} {e:>8.3f} {w1:>12.3f} {n:>7}")
    out = os.path.join(ROOT, "docs", "results", "real-images.json")
    with open(out, "w") as f:
        json.dump({"photos": ["china.jpg", "flower.jpg"], "licence": "CC BY 2.0 (via scikit-learn sample images)",
                   "object_level": 200, "rows": rows}, f, indent=1)
    print("wrote", os.path.normpath(out))


if __name__ == "__main__":
    main()
