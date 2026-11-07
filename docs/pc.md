# Running Siege on an x86-64 QNX target (and what is still untested for a real PC)

QNX SDP 8.0 targets x86-64 as well as aarch64, and the SDK can build a complete bootable x86-64 disk
image with networking and ssh (`mkqnximage`). That gives a second architecture, and a route to a spare PC.
This page records exactly what was run and what was not.

## What was verified, in emulation

Everything below ran on the Mac in `qemu-system-x86_64` (software emulation, 2 CPUs), against a real QNX 8.0
x86-64 system. It is **not** hardware.

1. **Build an image** in the Ubuntu VM: `mkqnximage --type=qemu --arch=x86_64 --noprompt --ssh-ident=<your .pub> --build`.
   This writes `output/disk-qemu` (a raw 150 MB disk image) and `output/ifs.bin`.
2. **Build Siege for x86-64** with the same source: `make ARCH=x86_64 BIN=build/x86_64/bin` (inside the VM,
   after `source ~/qnx800/qnxsdp-env.sh`). All programs compiled with no source changes.
3. **Boot it:**
   ```sh
   qemu-system-x86_64 -smp 2 -cpu max -m 1G -drive file=disk-qemu,format=raw,if=ide \
     -netdev user,id=net0,hostfwd=tcp:127.0.0.1:2222-:22 -device virtio-net-pci,netdev=net0 \
     -object rng-random,filename=/dev/urandom,id=rng0 -device virtio-rng-pci,rng=rng0 \
     -nographic -kernel ifs.bin
   ```
   The image reached `Startup complete`, started `sshd`, and accepted the key.
4. **Install and run over ssh**, the same path a physical board or PC would use:
   ```sh
   ./siege hw install root@127.0.0.1:2222 --bin build/x86_64/bin
   ./siege test --ssh root@127.0.0.1:2222 --remote-dir /data/siege --target-label emulator-x86_64 --profile none --json none.json
   ```
   `host:port` is accepted for a target behind a forwarded port, and `--target-label` keeps these results from being
   mistaken for hardware.

This is the first time the installer and the ssh transport ran against a real QNX target, not a stand-in.

## Results (5 runs each, 20 ms deadline, QNX x86-64 in QEMU)

Failed runs out of 5. Full report: [`../examples/x86/report.md`](../examples/x86/report.md).

| Scenario | None | `prio` | `isolate` | `budget` |
|---|---|---|---|---|
| baseline | 0/5 | 0/5 | 0/5 | 0/5 |
| CPU hog at priority 20 | 5/5 | 0/5 | 0/5 | 0/5 |
| `workflood` at priority 30 | 5/5 | 2/5 | 5/5 | 5/5 |
| AI neighbour at priority 20 | 5/5 | 0/5 | 0/5 | 0/5 |
| plain mutex held by a low-priority process | 5/5 | 5/5 | 5/5 | 5/5 |
| detector killed, no supervisor | 5/5 | 5/5 | 5/5 | 5/5 |
| detector killed, supervised | 1/5 | 0/5 | 0/5 | 0/5 |

The pattern matches the aarch64 results: CPU contention is fixed by every profile, the shared-service flood only by
the higher pipeline priority, and the lock and the unsupervised dead detector by none of them. (`prio` failed 2 of 5
here on the flood against 1 of 15 on aarch64; with 5 runs that is within noise, and I have not tested it further.)
Agreement between two emulated architectures supports the result being about QNX's scheduling and not about one CPU
model. It says nothing about hardware timing.

## What is not verified: booting on a physical PC

I have not booted this on a real machine. The image `mkqnximage` builds is made for QEMU's virtual hardware, so a PC
would need changes I have not tested:

| In the image | Why it will not work as is on a PC | What the SDK offers |
|---|---|---|
| `io-sock ... -d vtnet_pci` | virtio network card exists only in virtual machines | `devs-em`, `devs-igc`, `devs-ix`, `devs-ixl` (Intel), `devs-re` (Realtek), among others |
| `devb-eide` | a legacy IDE disk, which QEMU provides and most PCs do not | `devb-ahci` (SATA), `devb-nvme`, `devb-umass` (USB) |
| `devc-ser8250` shell | a serial console; many PCs have no serial port | `devc-con` for a screen console |

Booting also depends on whether the PC starts in legacy BIOS or UEFI mode, and `mkqnximage` has an image-type option for
that which I did not exercise. If you try it: write the disk image only to a USB stick you can afford to wipe, check the
device name twice (a wrong `dd` target destroys data), boot from USB without installing anything, and tell me what the
console prints. I would expect to need a round or two of fixes.
