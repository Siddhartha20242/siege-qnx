#!/usr/bin/env python3
"""Record a real dashboard run as an animated GIF.

    scripts/make_gif.py [--scenario "workflood @prio 30"] [--profiles none,isolate,prio]

Starts the live dashboard against the real emulator, runs the scenario under each
profile as one overlaid comparison, then captures the finished run one per-second
sample at a time with headless Chrome (in a throwaway profile, so it never touches
your own browser) and joins the frames into docs/live-dashboard.gif.

The frames are real recorded data replayed step by step: nothing is simulated.
"""
import argparse, json, os, subprocess, sys, tempfile, time, urllib.request
from PIL import Image

here = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser()
ap.add_argument("--scenario", default="workflood @prio 30")
ap.add_argument("--profiles", default="none,isolate,prio")
ap.add_argument("--port", type=int, default=8768)
ap.add_argument("--out", default=os.path.join(here, "..", "docs", "live-dashboard.gif"))
ap.add_argument("--chrome", default="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
ap.add_argument("--width", type=int, default=860)
args = ap.parse_args()

base = f"http://127.0.0.1:{args.port}"
tmp = tempfile.mkdtemp()
server = subprocess.Popen([sys.executable, os.path.join(here, "live.py"), "--port", str(args.port)],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def events(seconds=3):
    """Read the replayed event stream for a moment."""
    req = urllib.request.urlopen(f"{base}/events", timeout=seconds + 2)
    data, end = b"", time.time() + seconds
    req.fp.raw._sock.settimeout(1.0) if hasattr(req.fp, "raw") else None
    try:
        while time.time() < end:
            chunk = req.read1(65536) if hasattr(req, "read1") else req.read(4096)
            if not chunk:
                break
            data += chunk
    except Exception:
        pass
    finally:
        req.close()
    return [json.loads(l[6:]) for l in data.decode(errors="replace").splitlines() if l.startswith("data: ")]


try:
    for _ in range(60):
        try:
            if any(e["type"] == "ready" for e in events(2)):
                break
        except Exception:
            time.sleep(2)
    else:
        sys.exit("the dashboard never became ready")

    group = f"gif-{int(time.time())}"
    jobs = [{"scenario": args.scenario, "profile": p, "group": group} for p in args.profiles.split(",")]
    urllib.request.urlopen(urllib.request.Request(f"{base}/run", data=json.dumps({"jobs": jobs}).encode(), method="POST"))
    print("running", args.scenario, "under", args.profiles, flush=True)
    t0 = time.time()
    while time.time() - t0 < 240:
        time.sleep(4)
        evs = events(2)
        if evs and evs[-1]["type"] == "idle" or sum(1 for e in evs if e["type"] == "result") >= len(jobs):
            break
    samples = sum(1 for e in events(2) if e["type"] == "sample")
    print(f"recorded {samples} samples; capturing frames", flush=True)

    frames = []
    for k in range(0, samples + 1):
        png = os.path.join(tmp, f"f{k:03d}.png")
        subprocess.run([args.chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
                        f"--user-data-dir={os.path.join(tmp, 'profile')}", "--window-size=1100,980",
                        f"--screenshot={png}", f"{base}/?static=1&upto={k}"],
                       capture_output=True, timeout=40)
        im = Image.open(png).convert("RGB")
        h = int(im.height * args.width / im.width)
        frames.append(im.resize((args.width, h), Image.LANCZOS))
    durations = [600] * len(frames)
    durations[0], durations[-1] = 900, 4000
    quant = [f.quantize(colors=128, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE) for f in frames]
    quant[0].save(args.out, save_all=True, append_images=quant[1:], duration=durations, loop=0, optimize=True)
    print(f"wrote {os.path.normpath(args.out)}: {len(frames)} frames, {os.path.getsize(args.out)//1024} KB")
finally:
    server.terminate()
    try:
        server.wait(timeout=10)
    except subprocess.TimeoutExpired:
        server.kill()
