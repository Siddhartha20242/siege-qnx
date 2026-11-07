"""Drive a QNX guest in QEMU over its serial console.

    with Console("build/siege.ifs") as c:
        text = c.run("pipeline.sh 5")

Used by matrix.py and calibrate.py. The guest runs under software emulation
(QEMU virt, cortex-a57, 2 CPUs).
"""
import os, re, shutil, socket, subprocess, tempfile, time


class Console:
    def __init__(self, image, mem="512M", smp=2, boot_timeout=60):
        if not os.path.exists(image):
            raise SystemExit(f"siege: {image} not found. Build it first: ./siege build")
        if shutil.which("qemu-system-aarch64") is None:
            raise SystemExit("siege: qemu-system-aarch64 not found. macOS: brew install qemu; "
                             "Ubuntu: sudo apt install qemu-system-arm. ./siege doctor checks everything.")
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
        out = self.wait_for(rf"^END{self.seq}", timeout)
        if not re.search(rf"^END{self.seq}", out, re.M):          # never returned: interrupt it so the next command is clean
            self.sock.send(b"\x03")
            self.wait_for(rf"^END{self.seq}", 8)
        return out

    def close(self):
        self.qemu.kill()
        self.qemu.wait()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def split_host(host):
    """"user@host:2222" -> ("user@host", "2222"); no port -> (host, None). For targets behind a forwarded port, such as QEMU."""
    dest, _, port = host.rpartition(":")
    return (dest, port) if dest and port.isdigit() else (host, None)


class SSHShell:
    """Run commands on a real QNX target over ssh, with the same interface as Console.

        with SSHShell("root@192.168.1.50", "/data/siege") as c:
            text = c.run("pipeline.sh 5")

    The Siege programs and scripts must already be on the target (./siege hw install).
    """

    def __init__(self, host, remote_dir="/data/siege"):
        self.host, self.remote_dir = host, remote_dir
        self.dest, self.port = split_host(host)
        probe = self._ssh("true", 15)
        if probe.returncode != 0:
            raise SystemExit(f"siege: cannot reach {host} over ssh with a key: {probe.stderr.strip()}\n"
                             f"  Check the address, then install your key: ssh-copy-id {host}")

    def _ssh(self, command, timeout):
        port = ["-p", self.port] if self.port else []
        return subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8"] + port + [self.dest, command],
                              capture_output=True, text=True, timeout=timeout)

    def run(self, command, timeout=60):
        try:
            r = self._ssh(f"export PATH={self.remote_dir}:$PATH; {command}", timeout)
        except subprocess.TimeoutExpired as e:
            return (e.stdout or b"").decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
        return r.stdout + r.stderr

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
