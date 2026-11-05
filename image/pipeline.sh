#!/bin/ksh
# Run the reference pipeline for N seconds (default 10), optionally under attack.
#   pipeline.sh [seconds]
#   ATK="cpu flood" pipeline.sh 8
# Environment: SRC_PRIO DET_PRIO CTL_PRIO ATK_PRIO (default 10), DEADLINE_MS (15),
# TOL_PM tolerated late frames in per mille (20 = 2%), PROFILE (see below),
# ATK_DELAY seconds the pipeline runs alone before attackers start (default 1).
# Faults: KILL_AT=<s> kills the detector <s> seconds in; SUPERVISE=1 restarts it
# and reports the restart time; RECOVERY_MS is the longest tolerated silence.
# While it runs, `cat /dev/siege` shows the live status.
#
# The pipeline is started first and attacked while running. Launching the
# attacker first lets it starve the camera before its first frame is stamped,
# which hides the attack from every measurement.

# The orchestrator must outrank every attacker, or a CPU hog would starve this
# script. Re-run ourselves at a high priority; the pipeline processes then set
# their own priority.
if [ -z "$SIEGE_ORCH" ]; then
    SIEGE_ORCH=1 exec on -p 60r ksh /proc/boot/pipeline.sh "$@"
fi

DUR=${1:-10}
SRC_PRIO=${SRC_PRIO:-10}
DET_PRIO=${DET_PRIO:-10}
CTL_PRIO=${CTL_PRIO:-10}
ATK_PRIO=${ATK_PRIO:-10}
DEADLINE_MS=${DEADLINE_MS:-15}
TOL_PM=${TOL_PM:-20}       # tolerated late frames, per mille (20 = 2%)
ATK_DELAY=${ATK_DELAY:-1}

# Hardening profile: PROFILE=none|prio|isolate|budget
#   none     everything at the default round-robin priority 10
#   prio     the pipeline outranks its neighbours (priority 40)
#   isolate  the pipeline owns CPU 1, neighbours are confined to CPU 0
#   budget   neighbours are capped with SCHED_SPORADIC (10 ms per 100 ms)
PROFILE=${PROFILE:-none}
export PROFILE
SUPERVISE=${SUPERVISE:-0}
RECOVERY_MS=${RECOVERY_MS:-500}
case $PROFILE in
    none)    ;;
    prio)    SRC_PRIO=40; DET_PRIO=40; CTL_PRIO=40 ;;
    isolate) PIPE_CPU=1; ATK_CPU=0 ;;
    budget)  ATK_SS=${ATK_SS:-10:100} ;;
    *)       echo "pipeline.sh: unknown PROFILE '$PROFILE'"; exit 2 ;;
esac

# Emulator calibration: QEMU adds ~3 ms whenever an idle virtual CPU is woken,
# which real hardware does not. A priority-1 spinner per CPU keeps them busy
# without taking CPU from anything at priority 2 or above. Disable with IDLE_POLL=0.
IDLE_POLL=${IDLE_POLL:-1}

echo "RUN profile=$PROFILE atk=${ATK:-none} atk_prio=$ATK_PRIO dur=$DUR deadline_ms=$DEADLINE_MS atk_delay=$ATK_DELAY idle_poll=$IDLE_POLL"
if [ "$IDLE_POLL" = "1" ]; then
    attacker -m cpu -d $((DUR + 2)) -P 1 > /dev/null &
    IDLE_PID=$!
fi
# The status device lives for the whole boot; start it once.
if [ ! -e /dev/siege ]; then
    sieged &
    waitfor /dev/siege 5
fi
${PIPE_CPU:+on -C $PIPE_CPU} controller -P $CTL_PRIO -D $DEADLINE_MS -T $TOL_PM -R $RECOVERY_MS &
CTL_PID=$!
waitfor /dev/name/local/siege_ctl 5
if [ "$SUPERVISE" = "1" ] || [ -n "$KILL_AT" ]; then
    NORESTART=""
    [ "$SUPERVISE" = "1" ] || NORESTART="-r 0"
    ${PIPE_CPU:+on -C $PIPE_CPU} supervisor -P 50 ${KILL_AT:+-k $KILL_AT} $NORESTART -- detector -P $DET_PRIO &
else
    ${PIPE_CPU:+on -C $PIPE_CPU} detector -P $DET_PRIO &
fi
DET_PID=$!
waitfor /dev/name/local/siege_det 5
${PIPE_CPU:+on -C $PIPE_CPU} frame_src -d $DUR -P $SRC_PRIO &
SRC_PID=$!
ATK_PIDS=""

if [ -n "$ATK" ]; then
    sleep $ATK_DELAY
    for a in $ATK; do
        ${ATK_CPU:+on -C $ATK_CPU} attacker -m $a -d $((DUR - ATK_DELAY + 1)) -P $ATK_PRIO ${ATK_SS:+-s $ATK_SS} &
        ATK_PIDS="$ATK_PIDS $!"
    done
fi
wait $CTL_PID $DET_PID $SRC_PID $ATK_PIDS $IDLE_PID
