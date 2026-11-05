/* Scheduling probe: how long does a thread at a given priority go without a
 * CPU while something else is running?
 *
 *   probe -m spin  -d 4 -P 10 [-a cpumask]   busy loop, report gaps between clock reads
 *   probe -m sleep -d 4 -P 10 [-a cpumask]   20 ms periodic wakeups, report lateness
 *
 * Used to check that attackers behave as intended (see scripts/ and docs).
 */
#include "common.h"
#include <sys/syspage.h>

int main(int argc, char **argv)
{
    const char *mode = "spin";
    int duration_s = 4, prio = 10, c;
    unsigned long mask = 0;

    setvbuf(stdout, NULL, _IOLBF, 0);
    while ((c = getopt(argc, argv, "m:d:P:a:")) != -1) {
        switch (c) {
        case 'm': mode = optarg; break;
        case 'd': duration_s = atoi(optarg); break;
        case 'P': prio = atoi(optarg); break;
        case 'a': mask = strtoul(optarg, NULL, 0); break;
        }
    }

    uint64_t last = now_ns();                 /* before we can be starved */
    if (mask) ThreadCtl(_NTO_TCTL_RUNMASK, (void *)(uintptr_t)mask);
    int rc = set_prio(prio);
    uint64_t start = last, end = start + (uint64_t)duration_s * 1000000000ULL;
    uint32_t gaps = 0;
    uint64_t max_gap = 0;

    if (!strcmp(mode, "spin")) {
        for (;;) {
            uint64_t t = now_ns();
            uint64_t g = t - last;
            if (g > 1000000ULL) { gaps++; if (g > max_gap) max_gap = g; }
            last = t;
            if (t >= end) break;
        }
    } else {                                   /* sleep: mimic frame_src */
        uint64_t next = now_ns();
        while (next < end) {
            next += FRAME_PERIOD_NS;
            struct timespec ts = { .tv_sec = (time_t)(next / 1000000000ULL),
                                   .tv_nsec = (long)(next % 1000000000ULL) };
            clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &ts, NULL);
            uint64_t late = now_ns() - next;
            if (late > 5000000ULL) { gaps++; if (late > max_gap) max_gap = late; }
        }
    }

    printf("PROBE mode=%s cpus=%u prio=%d rc=%d mask=0x%lx gaps=%u max_gap_ms=%llu wall_ms=%llu\n",
           mode, (unsigned)_syspage_ptr->num_cpu, prio, rc, mask, gaps,
           (unsigned long long)(max_gap / 1000000ULL),
           (unsigned long long)((now_ns() - start) / 1000000ULL));
    return 0;
}
