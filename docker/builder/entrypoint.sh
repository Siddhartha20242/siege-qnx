#!/bin/sh
# Load the mounted QNX SDP, then run ./siege with the given arguments.
if [ -f "$SIEGE_SDP/qnxsdp-env.sh" ]; then
    . "$SIEGE_SDP/qnxsdp-env.sh" >/dev/null 2>&1
else
    echo "siege-in-docker: no QNX SDP at $SIEGE_SDP. Mount yours: -v \$HOME/qnx800:/opt/qnx800:ro" >&2
fi
exec ./siege "$@"
