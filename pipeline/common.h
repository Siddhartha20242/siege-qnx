/* Shared definitions for the Siege reference pipeline.
 *
 * frame_src --MsgSend--> detector --MsgSend--> controller
 *
 * Every frame is stamped at capture; the controller measures capture ->
 * command latency against DEADLINE_NS and counts late and lost frames.
 */
#ifndef SIEGE_COMMON_H
#define SIEGE_COMMON_H

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <errno.h>
#include <unistd.h>
#include <pthread.h>
#include <sched.h>
#include <sys/iomsg.h>
#include <sys/neutrino.h>
#include <sys/dispatch.h>

#define FRAME_W          32
#define FRAME_H          32
#define FRAME_PERIOD_NS  20000000ULL   /* 50 Hz */
#define DEADLINE_NS      15000000ULL   /* default capture -> command budget, 15 ms */
#define IPC_TIMEOUT_NS   5000000ULL    /* give up on a stuck peer after 5 ms */
#define STALL_NS         100000000ULL  /* controller starved if idle this long */

#define DET_NAME "siege_det"
#define CTL_NAME "siege_ctl"

/* Custom message types must be above the QNX I/O range. */
#define MSG_FRAME (_IO_MAX + 1)
#define MSG_DET   (_IO_MAX + 2)
#define MSG_STOP  (_IO_MAX + 3)
#define MSG_JUNK  (_IO_MAX + 9)        /* used only by the flood attacker */

typedef struct {
    uint16_t type;
    uint16_t pad;
    uint32_t seq;
    uint64_t t_capture_ns;
    uint8_t  px[FRAME_W * FRAME_H];
} frame_msg_t;

typedef struct {
    uint16_t type;
    uint16_t pad;
    uint32_t seq;
    uint64_t t_capture_ns;
    int16_t  x, y;
    int32_t  score;
} det_msg_t;

static inline uint64_t now_ns(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ULL + (uint64_t)ts.tv_nsec;
}

/* Give the calling thread a round-robin priority, the QNX default policy for
 * ordinary processes. Returns 0 on success. */
static inline int set_prio(int prio)
{
    struct sched_param sp;
    memset(&sp, 0, sizeof sp);
    sp.sched_priority = prio;
    return pthread_setschedparam(pthread_self(), SCHED_RR, &sp);
}

/* Set the priority and report what the kernel actually applied. */
static inline void set_prio_report(const char *who, int prio)
{
    int rc = set_prio(prio);
    struct sched_param sp;
    int pol = -1;
    memset(&sp, 0, sizeof sp);
    pthread_getschedparam(pthread_self(), &pol, &sp);
    printf("PRIO %s want=%d got=%d policy=%d rc=%d\n", who, prio, sp.sched_priority, pol, rc);
}

/* Bound the next blocking kernel call (send+reply) to ns. */
static inline void timeout_send_reply(uint64_t ns)
{
    TimerTimeout(CLOCK_MONOTONIC, _NTO_TIMEOUT_SEND | _NTO_TIMEOUT_REPLY,
                 NULL, &ns, NULL);
}

static inline int open_name(const char *name, int tries)
{
    int coid = -1;
    while (tries-- > 0) {
        coid = name_open(name, 0);
        if (coid != -1) return coid;
        usleep(100000);
    }
    return -1;
}

#endif
