#!/bin/ksh
# Generic launcher: attack any real-time program, not just the reference pipeline.
#
#   harness.sh <seconds> <command> [args...]
#   ATK=cpu ATK_PRIO=20 harness.sh 5 ticker -d 5
#
# The command is started first, and attackers join it ATK_DELAY seconds later
# (default 1), so the attack hits a program that is already running. The
# command must print the two lines Siege reads (see README, "Testing your own
# program"):
#
#   FINAL ... late=N lost=N stalls=N p50_us=N p99_us=N max_us=N
#   RESULT PASS|FAIL
#
# Environment: ATK (attacker modes), ATK_PRIO, ATK_DELAY, ATK_SS (budget as
# ms:ms), IDLE_POLL (emulator calibration, see pipeline.sh). Anything else in
# the environment, such as a priority variable your program reads, passes
# through untouched.

# Outrank every attacker so a CPU hog cannot starve this script.
if [ -z "$SIEGE_ORCH" ]; then
    SELF=$0
    case $SELF in /*) ;; *) SELF=$(whence -p "$SELF" 2>/dev/null) ;; esac
    [ -n "$SELF" ] || SELF=/proc/boot/harness.sh
    SIEGE_ORCH=1 exec on -p 60r ksh "$SELF" "$@"
fi

DUR=$1
shift
ATK_PRIO=${ATK_PRIO:-10}
ATK_DELAY=${ATK_DELAY:-1}
IDLE_POLL=${IDLE_POLL:-1}

echo "RUN pipeline=$1 atk=${ATK:-none} atk_prio=$ATK_PRIO dur=$DUR atk_delay=$ATK_DELAY idle_poll=$IDLE_POLL"

if [ "$IDLE_POLL" = "1" ]; then
    attacker -m cpu -d $((DUR + 2)) -P 1 > /dev/null &
    IDLE_PID=$!
fi

"$@" &
PIPE_PID=$!

ATK_PIDS=""
if [ -n "$ATK" ]; then
    sleep $ATK_DELAY
    for a in $ATK; do
        attacker -m $a -d $((DUR - ATK_DELAY + 1)) -P $ATK_PRIO ${ATK_SS:+-s $ATK_SS} &
        ATK_PIDS="$ATK_PIDS $!"
    done
fi
wait $PIPE_PID $ATK_PIDS $IDLE_PID
