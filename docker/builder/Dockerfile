# EXPERIMENTAL and unverified: written but never run with a real SDP (no Docker is installed on the author's machine).
# CI only checks that this image builds.
#
# The idea: on an Apple Silicon Mac, Docker Desktop can run an x86-64 container, so the QNX host tools
# could run there instead of in a UTM virtual machine. The SDP is not in the image and cannot be: you install
# it yourself (free QNX account) and mount it.
#
#   docker build --platform linux/amd64 -f docker/builder/Dockerfile -t siege-builder .
#   docker run --rm -it --platform linux/amd64 -v "$PWD":/siege -v "$HOME/qnx800":/opt/qnx800:ro siege-builder doctor
#   docker run --rm -it --platform linux/amd64 -v "$PWD":/siege -v "$HOME/qnx800":/opt/qnx800:ro siege-builder build
#
# The QNX tools may need more x86-64 libraries than are listed here; add what the first run reports.
FROM --platform=linux/amd64 ubuntu:24.04
RUN apt-get update && apt-get install -y --no-install-recommends \
        make rsync python3 python3-numpy qemu-system-arm openssh-client ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /siege
COPY docker/builder/entrypoint.sh /usr/local/bin/siege-in-docker
ENV SIEGE_SDP=/opt/qnx800
ENTRYPOINT ["siege-in-docker"]
CMD ["doctor"]
