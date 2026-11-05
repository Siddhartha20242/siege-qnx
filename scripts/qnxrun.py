#!/usr/bin/env python3
"""Boot build/siege.ifs, run one shell command on the QNX console, print output.

    scripts/qnxrun.py "pipeline.sh 8" [--until RESULT] [--timeout 90]

Stops when the --until marker appears (default: RESULT) or the timeout hits.
"""
import argparse, os, socket, subprocess, sys, tempfile, time

ap = argparse.ArgumentParser()
ap.add_argument("cmd")
ap.add_argument("--until", default="RESULT")
ap.add_argument("--timeout", type=float, default=90)
ap.add_argument("--image", default=os.path.join(os.path.dirname(__file__), "..", "build", "siege.ifs"))
args = ap.parse_args()

sock_path = os.path.join(tempfile.mkdtemp(), "qnx.sock")
qemu = subprocess.Popen(
    ["qemu-system-aarch64", "-machine", "virt,gic-version=3", "-cpu", "cortex-a57",
     "-smp", "2", "-m", "512M", "-nographic", "-monitor", "none",
     "-serial", f"unix:{sock_path},server=on,wait=off", "-kernel", args.image],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

try:
    for _ in range(50):
        if os.path.exists(sock_path):
            break
        time.sleep(0.1)
    s = socket.socket(socket.AF_UNIX)
    s.connect(sock_path)
    s.settimeout(0.5)

    buf = ""
    def pump():
        global buf
        try:
            d = s.recv(65536)
            if d:
                buf += d.decode(errors="replace")
        except socket.timeout:
            pass

    deadline = time.time() + args.timeout
    while time.time() < deadline and "Startup complete" not in buf:
        pump()
    time.sleep(2)
    pump()
    mark = len(buf)
    s.send((args.cmd + "\n").encode())

    while time.time() < deadline:
        pump()
        if args.until in buf[mark:]:
            time.sleep(1)
            pump()
            break
    sys.stdout.write(buf[mark:])
finally:
    qemu.kill()
    qemu.wait()
