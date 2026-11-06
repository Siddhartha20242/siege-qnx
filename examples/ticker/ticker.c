/* ticker: a second, unrelated real-time program to show Siege is not tied to
 * the reference pipeline.
 *
 * It is a single periodic task, like a motor-control tick: wake every 10 ms,
 * and count a tick as late if it starts more than DEADLINE_MS after it was
 * due. It prints the two lines Siege reads: FINAL and RESULT.
 *
 *   ticker -d seconds [-P prio]
 *
 * Environment: PIPE_PRIO (priority, overridden by -P), DEADLINE_MS (default 5),
 * TOL_PM (tolerated late ticks, per mille, default 20).
 */
#include "../../pipeline/common.h"

#define PERIOD_NS 10000000ULL           /* 100 Hz */
#define MAX_TICKS 65536

static uint32_t lat_us[MAX_TICKS];

static int cmp_u32(const void *a, const void *b)
{
    uint32_t x = *(const uint32_t *)a, y = *(const uint32_t *)b;
    return (x > y) - (x < y);
}

int main(int argc, char **argv)
{
    int duration_s = 5, c;
    int prio = getenv("PIPE_PRIO") ? atoi(getenv("PIPE_PRIO")) : 10;
    uint32_t deadline_ms = getenv("DEADLINE_MS") ? (uint32_t)atoi(getenv("DEADLINE_MS")) : 5;
    uint32_t tol_pm = getenv("TOL_PM") ? (uint32_t)atoi(getenv("TOL_PM")) : 20;

    setvbuf(stdout, NULL, _IOLBF, 0);
    while ((c = getopt(argc, argv, "d:P:")) != -1) {
        if (c == 'd') duration_s = atoi(optarg);
        else if (c == 'P') prio = atoi(optarg);
    }
    set_prio(prio);

    uint32_t ticks = (uint32_t)duration_s * (uint32_t)(1000000000ULL / PERIOD_NS);
    if (ticks > MAX_TICKS) ticks = MAX_TICKS;

    uint32_t late = 0;
    uint64_t next = now_ns();
    for (uint32_t i = 0; i < ticks; i++) {
        next += PERIOD_NS;
        struct timespec ts = { .tv_sec = (time_t)(next / 1000000000ULL),
                               .tv_nsec = (long)(next % 1000000000ULL) };
        clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &ts, NULL);

        /* Lateness is measured against when the tick was due, so a starved
         * task cannot hide by simply waking up later. */
        uint64_t l = now_ns() - next;
        lat_us[i] = (uint32_t)(l / 1000ULL);
        if (l > (uint64_t)deadline_ms * 1000000ULL) late++;
    }

    qsort(lat_us, ticks, sizeof lat_us[0], cmp_u32);
    uint32_t p50 = lat_us[ticks / 2];
    uint32_t p99 = lat_us[(ticks * 99) / 100 >= ticks ? ticks - 1 : (ticks * 99) / 100];
    uint32_t mx = lat_us[ticks - 1];
    uint32_t late_pm = ticks ? (uint32_t)(((uint64_t)late * 1000) / ticks) : 1000;

    printf("FINAL t=%d frames=%u late=%u lost=0 stalls=0 p50_us=%u p99_us=%u max_us=%u\n",
           duration_s, ticks, late, p50, p99, mx);
    printf("RESULT %s late_pm=%u tol_pm=%u\n", late_pm <= tol_pm ? "PASS" : "FAIL", late_pm, tol_pm);
    return 0;
}
