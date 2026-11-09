# QNX 8.0 on an Apple Silicon Mac, for $0

**What you will build:** a working QNX 8.0 development setup on an M-series
Mac, with no paid software and no spare hardware. You will cross-compile a
native QNX program, build a bootable QNX image, boot it in QEMU on your Mac,
and watch two threads exchange messages through the QNX kernel.

**Time:** about 2 to 4 hours of your own time, mostly downloads, plus the wait for your QNX licence, which is
decided by QNX and may not be instant.
**Disk space:** about 30 GB free (the VM disk is set to 64 GB but only grows as it fills).
**Cost:** nothing beyond the Mac you already own. UTM is free from its website (the App Store copy costs money), and QNX SDP
8.0 is free for non-commercial use through QNX Everywhere.

**What you will see at the end** (so you know the goal):

```
QNX localhost 8.0.0 2026/06/05-16:21:14EDT QEMU_virt aarch64le
Hello from QNX 8.0.0 on QEMU_virt
client: server got 'ping 0'
```

Every command in steps 6 to 8 was run from a clean build while writing this.
Steps 1 to 5 were done on a real machine (macOS on an M3 Pro, Ubuntu 24.04.5,
QNX SDP 8.0) and the fixes in the troubleshooting section are problems that
actually came up. **Not tested:** Intel Macs, other Apple chips than the M3 Pro, other Ubuntu versions, and a blank-VM run of
`vm-setup.sh` and Step 9 from start to finish (Step 9's commands are the ones used to produce every result in this
repository).

## Before you start

You need these from the start, so nothing surprises you later:

* A Mac with an M-series chip, **macOS 13 or later** (Rosetta for Linux needs it), and about 30 GB of free disk. If Rosetta is not
  installed on the Mac yet: `softwareupdate --install-rosetta --agree-to-license`.
* [Homebrew](https://brew.sh), which Step 8 uses to install QEMU. Check with `brew --version`; if it is missing, install it from the site first.
* [UTM](https://mac.getutm.app) (Step 1), a free app that runs virtual machines on a Mac, and the Ubuntu 24.04 Desktop for Arm64 ISO.
  "Apple Virtualization" is Apple's built-in way to run a Linux VM at near-native speed, and "Rosetta" is Apple's translator that lets
  that Arm Linux run the x86-64 QNX tools. UTM only offers the Rosetta option when Apple Virtualization is ticked (Step 1).
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

> **Before Step 2:** run `uname -r`. The Rosetta fix in this tutorial depends on the kernel: our machine worked on the 6.8 series and broke on 7.0
> (see the first troubleshooting row). If yours prints 7.x and Step 3's `hello` test fails, use the 6.8 kernel and adapt the exact version
> string to what `grub` lists on your machine; the one in the table will not be the same for you.

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
chmod +x qnx-setup-VERSION-linux.run      # use the exact file name you downloaded; a glob breaks if two files match
./qnx-setup-VERSION-linux.run
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

What the board-specific lines mean, so you know what to change for a different board:

| Line | Meaning |
|---|---|
| `[image=0x40080000]` | Where in memory the image is loaded. The QEMU `virt` machine's RAM starts at `0x40000000`. |
| `[virtual=aarch64le,raw]` | Build a raw, bootable image for 64-bit Arm, little-endian. |
| `startup-qemu-virt` | The board's startup code. A real board uses the startup program from its own board support package. |
| `procnto-smp-instr` | The kernel and process manager: multi-core and instrumented, so the kernel trace in the Siege project works. The options after it are procnto options; see the QNX documentation. |
| `devc-serpl011 -e -F 0x9000000,33` | The serial driver for the PL011 UART that QEMU `virt` provides, at address `0x9000000`, interrupt 33. This is what gives you the `#` prompt. |
| `[+script] startup-script` | The script that runs once the kernel is up. |

You should get a file of about 3.7 MB.

## Step 8. Boot it on your Mac

Copy the image out of the VM, in this order. `youruser` is the username you chose when you installed Ubuntu.

1. **In the VM**, find its address: `hostname -I` (use the first one). Make sure the SSH server runs:
   `systemctl is-active ssh` should print `active` (if you ran `vm-setup.sh` it already does; otherwise
   `sudo apt install -y openssh-server`). In UTM's network settings use **Shared Network**.
2. **On the Mac**, set up key-based login. `./siege` never asks for a password, so a password-only VM makes `./siege doctor` and `./siege setup`
   fail later in Step 9. If you have no key yet: `ssh-keygen -t ed25519`. Then:

   ```sh
   ssh-copy-id youruser@VM-ADDRESS
   ssh -o BatchMode=yes youruser@VM-ADDRESS echo ok      # must print ok with NO password prompt
   ```

3. **On the Mac**, install QEMU and check it, then copy the image (in the program you built, `hello` is the QNX program; the
   Ubuntu `hello` you used in Step 3 is a different one):

```sh
brew install qemu
qemu-system-aarch64 --version
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
| `./siege doctor` says it cannot reach the VM, or asks for a password | Key login is not set up: run `ssh-copy-id youruser@VM-ADDRESS`, then check `ssh -o BatchMode=yes youruser@VM-ADDRESS echo ok` prints `ok`. |
| `ssh` hangs or says no route to host | Use UTM's **Shared Network**, check the VM's address with `hostname -I`, and that `systemctl is-active ssh` says `active`. |
| `qemu-system-aarch64: command not found` | `brew install qemu`, then open a new terminal. |
| QEMU opens but the screen stays black | It has no graphics window by design: the console is your terminal. Wait up to a minute for the `#` prompt. |
| `mkifs` cannot find `hello` | Run it in the folder that holds the program you compiled in Step 6. |
| Timing is jittery | Expected under emulation. Compare runs against each other, and do not treat latencies as hardware numbers. |

## Where to go next

* Read the buildfile again and add a second program to the image.
* Replace the one-process example with a real server and client in two
  processes using `name_attach()` and `name_open()`.
* The [Siege project](../README.md) in this repository builds on this exact
  setup: a real-time pipeline, attackers that try to break its deadlines, and
  QNX scheduling features that restore them.
