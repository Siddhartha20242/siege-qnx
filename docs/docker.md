# Docker and CI

## What the container is for

```sh
docker build -t siege .
docker run --rm siege                 # ./siege show: every measured result, as a table
docker run --rm siege show secpol
docker run --rm siege selftest
```

The image holds Siege's host tools and the saved measurements. It runs anywhere Docker
does, with no QNX, no QEMU and no account, so a reviewer can read the evidence, run the tests and
rebuild the report in one command. `docker compose run --rm show` does the same.

To keep a report, mount a folder, because files written inside the container are lost when it exits:

```sh
mkdir -p out && docker run --rm -v "$PWD/out:/out" siege report $(docker run --rm --entrypoint python3 siege scripts/results_files.py) --out /out/report
```

**What it cannot hold.** The QNX SDP and any QNX boot image are not ours to redistribute, so
neither is in the image, and the attacks themselves still need QNX and QEMU (see the README).

## The builder image (experimental)

`docker/builder/Dockerfile` is an attempt to remove the Linux virtual machine from the Mac
setup: Docker Desktop can run an x86-64 container, which is where the QNX host tools run. You
install the SDP yourself and mount it; the image supplies `make`, `rsync`, QEMU and Python.

**This has not been run with a real SDP.** The author's machine has no Docker daemon. CI only
checks that the image builds. Treat it as a starting point and expect to add libraries the
QNX tools report missing. The supported route is still the [codelab](codelab-qnx-on-apple-silicon.md).

## CI

[`.github/workflows/ci.yml`](../.github/workflows/ci.yml) runs on GitHub's own runners, with no
QNX, on every push:

| Job | What it checks |
|---|---|
| `tests` | The tooling tests, and that `./siege show` prints |
| `evidence` | Every committed measurement still matches the outcome declared for it in the config, for the main matrix and the security-policy matrix (the job prints the case counts). It also builds the HTML report from the saved results and uploads it with the JUnit files |
| `docker` | The tools image builds and runs, and the builder image builds |

`evidence` is a consistency check on saved data: it guards the data and the declared expectations, not the attacks, and it can only fail if someone edits a result or an expectation so they disagree. If someone edits a result file or an
expectation so they disagree, the build fails. To run the attacks on every change you need a runner with the SDP
([`examples/ci/github-actions.yml`](../examples/ci/github-actions.yml)).

Two scenarios in the security-policy config (`cpu hog @prio 10`, `memory bandwidth @prio 10`)
had no prediction written before their runs, so their expectations were pinned afterwards from
the results. The config says so on each of them.

## Why there is no Kubernetes

Siege tests one QNX machine, in QEMU or on a board. A QNX target is not a pod, and the
interference it measures is between processes on one machine, so an orchestrator would add
files without adding anything a reader could use. If you run many boards, the JSON result files and the CI
step above are the part that scales, and they work from any scheduler.
