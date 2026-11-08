# QNX 8.0 on an Apple Silicon Mac, for $0

**What you will build:** a working QNX 8.0 development setup on an M-series
Mac, with no paid software and no spare hardware. You will cross-compile a
native QNX program, build a bootable QNX image, boot it in QEMU on your Mac,
and watch two threads exchange messages through the QNX kernel.

**Time:** about 2 hours, mostly downloads.
**Disk space:** about 30 GB free.
**Cost:** nothing. QNX SDP 8.0 is free for non-commercial use through QNX
Everywhere.

Every command in steps 6 to 8 was run from a clean build while writing this.
Steps 1 to 5 were done on a real machine (macOS on an M3 Pro, Ubuntu 24.04.5,
QNX SDP 8.0) and the fixes in the troubleshooting section are problems that
actually came up.

## Before you start

You need these from the start, so nothing surprises you later:

* A Mac with an M-series chip and about 30 GB of free disk.
* [Homebrew](https://brew.sh), which Step 8 uses to install QEMU.
* [UTM](https://mac.getutm.app) (Step 1) and the Ubuntu 24.04 Desktop for Arm64 ISO.
* A free qnx.com account (Step 4). Use the Ubuntu **desktop** in the VM: the QNX
  Software Center installer is a graphical program.

## How it fits together

The QNX SDP 8.0 build tools (`qcc`, `mkifs`) run on x86-64 Linux or Windows.
There is no macOS version and no Arm Linux version. An Apple Silicon Mac can
still use them:

```
 Mac (Apple Silicon)
 ├── UTM virtual machine: Ubuntu 24.04 for Arm
 │     └── Rosetta runs the x86-64 QNX tools   -> qcc, mkifs build a QNX image
 └── QEMU (native on macOS)                    -> boots that image (aarch64)
```

The program you build targets 64-bit Arm (`aarch64le`), which is also what
QEMU's `virt` machine emulates, so nothing is emulated twice.

## Step 1. Create the Ubuntu VM

1. Install [UTM](https://mac.getutm.app) (free from the website).
2. Download the **Ubuntu 24.04 Desktop for Arm64** ISO from ubuntu.com.
3. In UTM choose **Virtualize**, then **Linux**, and pick the ISO.
4. Give it generous resources. We suggest 4 or more CPUs, 8 GB of RAM and a
   64 GB disk.
5. In the Linux settings tick **Use Apple Virtualization** and **Enable
   Rosetta**. This exposes Apple's Rosetta translator to the guest.
6. Install Ubuntu as usual.

If the screen is black for several minutes at the first boot, wait. It
eventually shows the installer.

## Shortcut for Steps 2 and 3

Steps 2 and 3 (Rosetta, the amd64 libraries, the SSH server) are scripted. Inside
the Ubuntu VM, after Step 1:

```sh
curl -fsSL https://raw.githubusercontent.com/Siddhartha20242/siege-qnx/main/scripts/vm-setup.sh -o vm-setup.sh
bash vm-setup.sh --check   # reports what is missing, changes nothing
bash vm-setup.sh           # does it; asking for sudo
```

(No network access to GitHub from the VM? Copy `scripts/vm-setup.sh` from your clone with `scp` instead.)

It checks each step first, so it is safe to run twice, and it ends by printing the
address to give `./siege setup`. It does not do the QNX account, licence or Software
Center login (Steps 4 and 5), which need you. If you want to see what each step does,
the manual version follows.

## Step 2. Turn on Rosetta inside Ubuntu

Mount the Rosetta share and make it permanent:

```sh
sudo mkdir -p /media/rosetta
sudo mount -t virtiofs rosetta /media/rosetta
echo 'rosetta /media/rosetta virtiofs ro,nofail 0 0' | sudo tee -a /etc/fstab
```

Register Rosetta as the handler for x86-64 programs:

```sh
sudo apt update && sudo apt install -y binfmt-support
sudo update-binfmts --install rosetta /media/rosetta/rosetta \
  --magic "\x7fELF\x02\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x02\x00\x3e\x00" \
  --mask  "\xff\xff\xff\xff\xff\xfe\xfe\x00\xff\xff\xff\xff\xff\xff\xff\xff\xfe\xff\xff\xff" \
  --credentials yes --preserve no --fix-binary yes
```

**Check:**

```sh
cat /proc/sys/fs/binfmt_misc/rosetta
```

It should start with `enabled` and name `/media/rosetta/rosetta` as the
interpreter.

## Step 3. Let Ubuntu install x86-64 libraries

The QNX tools are x86-64 programs, so Ubuntu needs x86-64 copies of the
libraries they use. Add the `amd64` architecture:

```sh
sudo dpkg --add-architecture amd64
```

Ubuntu for Arm only has an Arm package mirror, so restrict the existing
sources to `arm64` and add the main mirror for `amd64`:

```sh
sudo sed -i '/^Types: deb/a Architectures: arm64' /etc/apt/sources.list.d/ubuntu.sources
sudo tee /etc/apt/sources.list.d/amd64.sources >/dev/null <<'EOF'
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
EOF
sudo apt update
```

(If your `ubuntu.sources` already has `Architectures:` lines, skip the `sed`.)

**Check** that an x86-64 program runs:

```sh
sudo apt install -y hello:amd64
hello
```

It should print `Hello, world!`. If it prints an error about an "unhandled
auxiliary vector", see the first troubleshooting entry.

## Step 4. Get a QNX licence and the installer

1. Create a free account at [qnx.com](https://www.qnx.com) (myQNX).
2. Request the free non-commercial licence through
   [QNX Everywhere](https://www.qnx.com/getqnx).
3. In your myQNX **License Manager**, accept the licence agreement and make
   sure the licence is deployed to your own user. The QNX Software Center will
   not offer downloads until it is.
4. Download the **QNX Software Center for Linux hosts** installer (a `.run`
   file) from the same site.

Install the Software Center's GUI libraries first. It is a Java/SWT program
and needs the x86-64 GTK stack:

```sh
sudo apt install -y libgtk-3-0t64:amd64 libcanberra-gtk3-module:amd64 \
  libasound2t64:amd64 libgl1:amd64 libxtst6:amd64
```

Then run the installer **from a terminal** (double-clicking opens it as text):

```sh
chmod +x qnx-setup-*-linux.run
./qnx-setup-*-linux.run
```

Accept the terms and install into `~/qnx`.

## Step 5. Install QNX SDP 8.0

```sh
~/qnx/qnxsoftwarecenter/qnxsoftwarecenter
```

1. Log in with your myQNX account.
2. Create a new installation for **QNX SDP 8.0** in `~/qnx800` and let it
   download (about 3.5 GB installed).
3. In the **Available** tab, search for `qemu` and also install **QNX SDP 8.0
   QEMU Virtualization Drivers (Startup)**. It provides `startup-qemu-virt`,
   the board startup code for QEMU. Without it the image build in step 7
   fails.

**Check:**

```sh
source ~/qnx800/qnxsdp-env.sh
qcc -V 2>&1 | head -20
ls $QNX_TARGET/aarch64le/boot/sys/startup-qemu-virt
```

You should see the `gcc_ntoaarch64le` toolchain listed and the startup file
should exist. Run the `source` line in every new terminal before using QNX
tools.

If the SDP ends up anywhere other than `~/qnx800`, remember its path: Step 9 needs it as `SIEGE_SDP`.

## Step 6. Your first QNX program

QNX is a microkernel: threads and processes talk by sending messages. A
client blocks in `MsgSend()` until a server answers with `MsgReply()`. The
program below does both sides in one process.

Save it as `hello.c` (it is also in this repository as
[`codelab/hello.c`](../codelab/hello.c)):

```c
#include <stdio.h>
#include <string.h>
#include <pthread.h>
#include <sys/neutrino.h>
#include <sys/utsname.h>

static int chid;                       /* the server's channel */

static void *server(void *arg)
{
    char buf[64], reply[96];
    (void)arg;

    for (int i = 0; i < 3; i++) {
        int rcvid = MsgReceive(chid, buf, sizeof buf, NULL);   /* wait for a client */
        snprintf(reply, sizeof reply, "server got '%s'", buf);
        MsgReply(rcvid, 0, reply, strlen(reply) + 1);          /* unblock the client */
    }
    return NULL;
}

int main(void)
{
    struct utsname u;
    uname(&u);
    printf("Hello from %s %s on %s\n", u.sysname, u.release, u.machine);

    chid = ChannelCreate(0);
    pthread_t t;
    pthread_create(&t, NULL, server, NULL);

    int coid = ConnectAttach(0, 0, chid, _NTO_SIDE_CHANNEL, 0);  /* connect to our own channel */
    for (int i = 0; i < 3; i++) {
        char msg[32], reply[96];
        snprintf(msg, sizeof msg, "ping %d", i);
        MsgSend(coid, msg, strlen(msg) + 1, reply, sizeof reply);  /* blocks until the reply */
        printf("client: %s\n", reply);
    }

    pthread_join(t, NULL);
    return 0;
}
```

Cross-compile it for 64-bit Arm:

```sh
source ~/qnx800/qnxsdp-env.sh
qcc -Vgcc_ntoaarch64le -o hello hello.c
file hello
```

`file` should report `ELF 64-bit LSB pie executable, ARM aarch64` with the
interpreter `/usr/lib/ldqnx-64.so.2`. That is a QNX executable. It will not
run on Linux.

## Step 7. Build a bootable QNX image

A QNX image bundles the kernel, the startup code, drivers, shared libraries
and your program into one file. You describe it in a *buildfile*. Save this as
`hello.build` (also in [`codelab/hello.build`](../codelab/hello.build)):

```
[search=${QNX_TARGET}/aarch64le:${QNX_TARGET}/aarch64le/boot/sys:${QNX_TARGET}:.]
[+dupignore]
[+optional]
[uid=0 gid=0 dperms=0555 perms=0555]

# 1. The kernel and the board startup code (QEMU "virt" machine).
[image=0x40080000]
[virtual=aarch64le,raw] boot = {
    startup-qemu-virt
    PATH=/proc/boot
    LD_LIBRARY_PATH=/proc/boot
    [+keeplinked uid=0 gid=0 perms=0700] CONFIG_PATH=/proc/boot procnto-smp-instr -mr -d 0777 -u 0777
}

# 2. What runs at boot: a serial console driver and a shell on it.
[+script] startup-script = {
    procmgr_symlink /proc/boot/ldqnx-64.so.2 /usr/lib/ldqnx-64.so.2
    TERM=qansi
    HOME=/tmp
    display_msg "Booting"
    pipe -U 24:24
    waitfor /dev/pipe
    slogger2 -U 21:21
    waitfor /dev/slog
    devc-serpl011 -e -F 0x9000000,33
    waitfor /dev/ser1
    on -d -t /dev/ser1 ksh -l
    display_msg "Startup complete"
    reopen /dev/ser1
}

# 3. Tools you will use at the prompt.
toybox=usr/bin/toybox
[type=link] ls=toybox
[type=link] cat=toybox
[type=link] echo=toybox
[type=link] uname=toybox
bin/on
[type=link] waitfor=on
bin/ksh
[type=link] sh=ksh
bin/pidin
bin/slogger2
sbin/pipe
sbin/devc-serpl011
usr/bin/getconf
[type=link] setconf=getconf

# 4. Shared libraries those programs need.
[-autolink]
lib/libc.so.6
usr/lib/ldqnx-64.so.2
lib/libgcc_s.so.1
lib/libm.so.3
lib/libslog2.so.1
[type=link] libslog2.so=libslog2.so.1
lib/libslog2shim.so.1
lib/libsecpol.so.1
lib/libjson.so.1
lib/libslog2parse.so.1
lib/libjail.so.1
lib/libregex.so.1
lib/libfsnotify.so.1
usr/lib/libz.so.2
[type=link] /bin/ksh=/proc/boot/ksh
[type=link] /bin/sh=/proc/boot/ksh

# 5. Your program, built in step 6.
[perms=0555] hello=hello
```

Section 1 is the heart of it: `startup-qemu-virt` sets up the hardware and
`procnto-smp-instr` is the QNX microkernel and process manager. The rest is
the services and files that exist after boot, and everything is kept in RAM.

Build the image:

```sh
mkifs hello.build hello.ifs
ls -lh hello.ifs
```

You should get a file of about 3.7 MB.

## Step 8. Boot it on your Mac

First check that the Mac can reach the VM: `ssh youruser@VM-ADDRESS echo ok` should print `ok`. In UTM's network settings use **Shared Network**; if it hangs, see the UTM network documentation.

Copy the image out of the VM. Its SSH server is already running if you ran
`vm-setup.sh`; otherwise install it once (`sudo apt install -y openssh-server`).
Find the VM's address with `hostname -I`. Then on the Mac:

```sh
brew install qemu
scp youruser@VM-ADDRESS:hello.ifs .
```

Boot it:

```sh
qemu-system-aarch64 -machine virt,gic-version=3 -cpu cortex-a57 \
  -smp 2 -m 512M -nographic -kernel hello.ifs
```

After a few seconds you get a `#` prompt. You are inside QNX. Try:

```
uname -a
hello
```

```
QNX localhost 8.0.0 2026/06/05-16:21:14EDT QEMU_virt aarch64le
Hello from QNX 8.0.0 on QEMU_virt
client: server got 'ping 0'
client: server got 'ping 1'
client: server got 'ping 2'
```

Press **Ctrl-A, then x** to quit QEMU.

That is the full loop: edit on the Mac, cross-compile in the VM, build an
image, boot it in QEMU.

## Step 9. Run Siege on what you just built

Everything above is the foundation the Siege project uses. On the Mac:

```sh
git clone https://github.com/Siddhartha20242/siege-qnx && cd siege-qnx
./siege setup youruser@VM-ADDRESS    # the VM from Step 1; it checks the SDP and tells you what is missing
./siege doctor                       # everything should say ok
./siege build                        # cross-compile in the VM, build build/siege.ifs here
./siege live                         # open http://127.0.0.1:8766, pick "workflood @prio 30", press Run
```

The repository only needs to be on the Mac; `./siege build` copies the sources into
the VM and brings the image back. If the SDP is not in `~/qnx800` in the VM, set
`SIEGE_SDP=/path/to/qnx800` first.

## Troubleshooting

These are the problems we hit, in the order they appeared.

| Symptom | Cause and fix |
|---|---|
| `update-binfmts: command not found` | Install `binfmt-support` (step 2). |
| `hello` prints `unhandled auxiliary vector type 29` (Rosetta fails) | On our machine the newer kernel the installer offered (7.0) broke Rosetta, while the 6.8 GA kernel worked. We did not find the root cause. Install `linux-image-generic`, check `uname -r` shows 6.8, and if needed pin the default boot entry in `/etc/default/grub`, for example `GRUB_DEFAULT="Advanced options for Ubuntu>Ubuntu, with Linux 6.8.0-147-generic"`, then run `sudo update-grub`. |
| The Software Center fails with `UnsatisfiedLinkError` about SWT or GTK | The x86-64 GTK libraries are missing. Install the packages in step 4. |
| Downloads say you must have a licence | The licence is not deployed to your user yet. Finish step 4.3. |
| Double-clicking the `.run` file opens a text editor | Run it from a terminal (step 4). |
| `Host file 'startup-qemu-virt' not available` | Install **QNX SDP 8.0 QEMU Virtualization Drivers (Startup)** (step 5.3). |
| `mkqnximage` warns that `sbin/devb-virtio` is missing | In our install the virtio disk driver was not present, so disk images from `mkqnximage` cannot mount their disk. This guide avoids it by booting a RAM-only image built with `mkifs`. If you pass `--ssh-ident` to `mkqnximage`, use `$HOME/...`, not `~/...`, because the tilde is not expanded. |
| QEMU crashes at boot with `gic_v3.c ... ASSERT(... use_memory_mapped_callouts ...)` | You enabled hardware acceleration (`-accel hvf`). The QNX startup code takes a GIC path that HVF's interrupt controller does not support. Leave acceleration off, as in step 8. It runs in software emulation, which is slower but works. |
| Timing is jittery | Expected under emulation. Compare runs against each other, and do not treat latencies as hardware numbers. |

## Where to go next

* Read the buildfile again and add a second program to the image.
* Replace the one-process example with a real server and client in two
  processes using `name_attach()` and `name_open()`.
* The [Siege project](../README.md) in this repository builds on this exact
  setup: a real-time pipeline, attackers that try to break its deadlines, and
  QNX scheduling features that restore them.
