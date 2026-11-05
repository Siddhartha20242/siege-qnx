#!/bin/sh
# Build, then boot interactively. Quit QEMU with Ctrl-A then x.
#   scripts/run.sh        rebuild and boot
#   scripts/run.sh -n     boot the existing image
cd "$(dirname "$0")/.."
[ "$1" = "-n" ] || scripts/build.sh || exit 1
exec qemu-system-aarch64 -machine virt,gic-version=3 -cpu cortex-a57 \
    -smp 2 -m 512M -nographic -kernel build/siege.ifs
