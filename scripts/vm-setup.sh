#!/bin/bash
# Prepare a fresh Ubuntu 24.04 Arm VM (UTM, Apple Virtualization) to run the x86-64 QNX tools.
# Steps 2, 3 and the SSH server of docs/codelab-qnx-on-apple-silicon.md, in one go.
#
#   bash vm-setup.sh          do it (asks for sudo)
#   bash vm-setup.sh --check  only report what is already in place, change nothing
#
# Safe to run twice: each step checks first. What it cannot do for you: the myQNX
# account and licence, and the QNX Software Center login, which need you.
set -u
CHECK=0; [ "${1:-}" = "--check" ] && CHECK=1
ok()   { printf '  [ok] %s\n' "$1"; }
todo() { printf '  [..] %s\n' "$1"; }
bad=0

step() {   # step "what" "test command" "do command"
    if eval "$2" >/dev/null 2>&1; then ok "$1"; return; fi
    if [ $CHECK = 1 ]; then todo "$1 (missing)"; bad=1; return; fi
    todo "$1 ..."
    if eval "$3"; then ok "$1"; else printf '  [no] %s failed\n' "$1"; bad=1; fi
}

[ "$(uname -m)" = "aarch64" ] || { echo "This is for an Arm Ubuntu VM (uname -m says $(uname -m))."; exit 2; }
echo "QNX host setup for Ubuntu on Apple Silicon"

step "Rosetta share mounted at /media/rosetta" "test -x /media/rosetta/rosetta" \
     "sudo mkdir -p /media/rosetta && sudo mount -t virtiofs rosetta /media/rosetta"
step "Rosetta mount is permanent" "grep -q '^rosetta ' /etc/fstab" \
     "echo 'rosetta /media/rosetta virtiofs ro,nofail 0 0' | sudo tee -a /etc/fstab >/dev/null"
step "binfmt-support installed" "dpkg -s binfmt-support" "sudo apt-get update -qq && sudo apt-get install -y binfmt-support"
step "Rosetta registered for x86-64 programs" "grep -q enabled /proc/sys/fs/binfmt_misc/rosetta" \
     "sudo update-binfmts --install rosetta /media/rosetta/rosetta \
      --magic '\x7fELF\x02\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x02\x00\x3e\x00' \
      --mask '\xff\xff\xff\xff\xff\xfe\xfe\x00\xff\xff\xff\xff\xff\xff\xff\xff\xfe\xff\xff\xff' \
      --credentials yes --preserve no --fix-binary yes"
step "amd64 architecture enabled" "dpkg --print-foreign-architectures | grep -q amd64" "sudo dpkg --add-architecture amd64"
step "Arm sources restricted to arm64" "grep -q '^Architectures: arm64' /etc/apt/sources.list.d/ubuntu.sources" \
     "sudo sed -i '/^Types: deb/a Architectures: arm64' /etc/apt/sources.list.d/ubuntu.sources"
step "amd64 package sources added" "test -f /etc/apt/sources.list.d/amd64.sources" \
     "sudo tee /etc/apt/sources.list.d/amd64.sources >/dev/null <<'SRC'
Types: deb
Architectures: amd64
URIs: http://archive.ubuntu.com/ubuntu/
Suites: noble noble-updates noble-backports
Components: main restricted universe multiverse
Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg

Types: deb
Architectures: amd64
URIs: http://security.ubuntu.com/ubuntu/
Suites: noble-security
Components: main restricted universe multiverse
Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg
SRC
sudo apt-get update -qq"
step "an x86-64 program runs (hello:amd64)" "hello" "sudo apt-get install -y hello:amd64 && hello"
step "GUI libraries for the QNX Software Center" "dpkg -s libgtk-3-0t64:amd64" \
     "sudo apt-get install -y libgtk-3-0t64:amd64 libcanberra-gtk3-module:amd64 libasound2t64:amd64 libgl1:amd64 libxtst6:amd64"
step "make and rsync installed" "command -v make && command -v rsync" "sudo apt-get install -y make rsync"
step "SSH server (so your Mac can reach the VM)" "systemctl is-active ssh" "sudo apt-get install -y openssh-server"

echo
if [ -d "$HOME/qnx800" ] && [ -f "$HOME/qnx800/qnxsdp-env.sh" ]; then ok "QNX SDP 8.0 found in ~/qnx800"
else todo "QNX SDP 8.0 not installed yet: do codelab Step 4 and 5 (myQNX account, licence, Software Center). That part needs you."; fi
echo
echo "Your VM address (for ./siege setup user@address on the Mac): $(whoami)@$(hostname -I | awk '{print $1}')"
[ $bad = 0 ] && echo "Host setup is complete." || echo "Some steps are missing; see above."
exit $bad
