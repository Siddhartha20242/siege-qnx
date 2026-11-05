#!/bin/sh
# Sync the repo to the Ubuntu VM, cross-compile, and build build/siege.ifs here.
set -e
cd "$(dirname "$0")/.."
VM=${SIEGE_VM:-siddhartha07@192.168.64.2}

mkdir -p build
ssh "$VM" 'mkdir -p ~/siege/src'
rsync -az --delete --exclude .git --exclude build ./ "$VM":siege/src/
ssh "$VM" 'source ~/qnx800/qnxsdp-env.sh >/dev/null 2>&1; cd ~/siege/src && make -s && mkifs image/ram.build build/siege.ifs'
scp -q "$VM":siege/src/build/siege.ifs build/siege.ifs
echo "built build/siege.ifs"
