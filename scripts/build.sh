#!/bin/sh
# Cross-compile Siege and build build/siege.ifs.
#
# Two ways to run it:
#   * the QNX SDP environment is loaded (source ~/qnx800/qnxsdp-env.sh): build here;
#   * otherwise: build on a machine that has the SDP, over ssh. The machine comes
#     from $SIEGE_VM or the file .siege-vm (write it with `./siege setup user@host`).
#
# Lines in image/local.build (optional, not committed) are appended to the image
# buildfile, so your own programs can be added without editing image/ram.build.
set -e
cd "$(dirname "$0")/.."

STEPS='make -s && for p in image/secpol/*.secpol; do secpolcompile -m -o build/secpol-$(basename $p .secpol).bin $p || exit 1; done && rm -f build/secpol-probe-*.bin && for p in image/secpol-probe/*.secpol; do if [ -e "$p" ]; then secpolcompile -m -o build/secpol-$(basename $p .secpol).bin $p || echo "compiler refused $p"; fi; done && cat image/ram.build $(ls image/local.build 2>/dev/null) > build/image.build && for b in build/secpol-probe-*.bin; do if [ -e "$b" ]; then echo "[perms=0444] $(basename $b)=$b" >> build/image.build; fi; done && mkifs build/image.build build/siege.ifs'
mkdir -p build

if [ -n "$QNX_TARGET" ] && command -v qcc >/dev/null 2>&1; then
    sh -c "$STEPS"
    echo "built build/siege.ifs"
    exit 0
fi

VM=${SIEGE_VM:-$(cat .siege-vm 2>/dev/null)}
SDP=${SIEGE_SDP:-'~/qnx800'}
if [ -z "$VM" ]; then
    echo "siege: no build machine configured." >&2
    echo "  Run:  ./siege setup user@host    (a machine with the QNX SDP installed)" >&2
    echo "  or load the SDP environment first and build here:  source ~/qnx800/qnxsdp-env.sh" >&2
    exit 1
fi
if ! ssh -o BatchMode=yes -o ConnectTimeout=8 "$VM" true 2>/dev/null; then
    echo "siege: cannot reach $VM over ssh with a key (no password prompts allowed)." >&2
    echo "  Check the address, then install your key:  ssh-copy-id $VM" >&2
    echo "  ./siege doctor explains each check." >&2
    exit 1
fi

ssh "$VM" 'mkdir -p ~/siege/src'
rsync -az --delete --exclude .git --exclude .notes --exclude build ./ "$VM":siege/src/
ssh "$VM" "source $SDP/qnxsdp-env.sh >/dev/null 2>&1; cd ~/siege/src && $STEPS"
scp -q "$VM":siege/src/build/siege.ifs build/siege.ifs
mkdir -p build/bin && rsync -az "$VM":siege/src/build/bin/ build/bin/
echo "built build/siege.ifs"
