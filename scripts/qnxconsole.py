"""Drive a QNX guest in QEMU over its serial console.

    with Console("build/siege.ifs") as c:
        text = c.run("pipeline.sh 5")

Used by matrix.py and calibrate.py. The guest runs under software emulation
(QEMU virt, cortex-a57, 2 CPUs).
"""
import os, re, socket, subprocess, tempfile, time


class Console:
    def __init__(self, image, mem="512M", smp=2, boot_timeout=60):
        self.buf = ""
        self.seq = 0
        self.sock_path = os.path.join(tempfile.mkdtemp(), "qnx.sock")
        self.qemu = subprocess.Popen(
            ["qemu-system-aarch64", "-machine", "virt,gic-version=3", "-cpu", "cortex-a57",
             "-smp", str(smp), "-m", mem, "-nographic", "-monitor", "none",
             "-serial", f"unix:{self.sock_path},server=on,wait=off", "-kernel", image],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(100):
            if os.path.exists(self.sock_path):
                break
            time.sleep(0.1)
        self.sock = socket.socket(socket.AF_UNIX)
        self.sock.connect(self.sock_path)
        self.sock.settimeout(0.5)
        self.wait_for(r"Startup complete", boot_timeout)
        time.sleep(2)

    def _pump(self):
        try:
            data = self.sock.recv(65536)
            if data:
                self.buf += data.decode(errors="replace")
        except socket.timeout:
            pass

    def wait_for(self, pattern, timeout):
        """Wait for a regex to appear in new output; return the new text."""
        mark = len(self.buf)
        end = time.time() + timeout
        while time.time() < end:
            self._pump()
            if re.search(pattern, self.buf[mark:], re.M):
                break
        return self.buf[mark:]

    def run(self, command, timeout=60):
        """Run one shell command on the guest and return its output."""
        self.seq += 1
        self.sock.send((f'{command}; echo EN""D{self.seq}\n').encode())
        return self.wait_for(rf"^END{self.seq}", timeout)

    def close(self):
        self.qemu.kill()
        self.qemu.wait()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
