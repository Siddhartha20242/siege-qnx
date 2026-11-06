/* pipeprobe: a real-time loop whose latency goes through a QNX system service.
 *
 * QNX pipes are served by the `pipe` resource manager, so every write and read
 * on a pipe is a message to that process. This program is a periodic producer
 * and a consumer joined by a pipe; it measures how long each 8-byte token takes
 * from the instant it was due to the instant the consumer reads it, and counts
 * a token as late past DEADLINE_MS. It prints the two lines Siege reads.
 *
 *   pipeprobe -d seconds [-P prio]
 *
 * Environment: PIPE_PRIO (default 10), DEADLINE_MS (default 5), TOL_PM (20).
 */
#include "../../pipeline/common.h"

#define PERIOD_NS 10000000ULL           /* 100 Hz */
#define MAX_TICKS 65536

static uint32_t lat_us[MAX_TICKS];
static int fds[2];
static uint32_t ticks;
static volatile uint32_t received;
static int prio;
static uint32_t deadline_ms;
static volatile uint32_t late;

static int cmp_u32(const void *a, const void *b)
{
    uint32_t x = *(const uint32_t *)a, y = *(const uint32_t *)b;
    return (x > y) - (x < y);
}

static void *consumer(void *arg)
{
    (void)arg;
    set_prio(prio);
    for (uint32_t i = 0; i < ticks; i++) {
        uint64_t due;
        if (read(fds[0], &due, sizeof due) != (ssize_t)sizeof due) break;
        uint64_t l = now_ns() - due;
        lat_us[i] = (uint32_t)(l / 1000ULL);
        if (l > (uint64_t)deadline_ms * 1000000ULL) late++;
        received++;
    }
    return NULL;
}

int main(int argc, char **argv)
{
    int duration_s = 5, c;
    prio = getenv("PIPE_PRIO") ? atoi(getenv("PIPE_PRIO")) : 10;
    deadline_ms = getenv("DEADLINE_MS") ? (uint32_t)atoi(getenv("DEADLINE_MS")) : 5;
    uint32_t tol_pm = getenv("TOL_PM") ? (uint32_t)atoi(getenv("TOL_PM")) : 20;

    setvbuf(stdout, NULL, _IOLBF, 0);
    while ((c = getopt(argc, argv, "d:P:")) != -1) {
        if (c == 'd') duration_s = atoi(optarg);
        else if (c == 'P') prio = atoi(optarg);
    }
    set_prio(prio);
    if (pipe(fds) == -1) { perror("pipeprobe: pipe"); return 1; }

    ticks = (uint32_t)duration_s * (uint32_t)(1000000000ULL / PERIOD_NS);
    if (ticks > MAX_TICKS) ticks = MAX_TICKS;

    pthread_t th;
    pthread_create(&th, NULL, consumer, NULL);

    uint64_t next = now_ns();
    for (uint32_t i = 0; i < ticks; i++) {
        next += PERIOD_NS;
        struct timespec ts = { .tv_sec = (time_t)(next / 1000000000ULL), .tv_nsec = (long)(next % 1000000000ULL) };
        clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &ts, NULL);
        uint64_t due = next;                       /* lateness counts from when the token was due */
        if (write(fds[1], &due, sizeof due) != (ssize_t)sizeof due) break;
    }

    /* Give the consumer a moment to drain, then stop it if the pipe is stuck. */
    for (int i = 0; i < 300 && received < ticks; i++) usleep(10000);
    uint32_t got = received;
    if (got < ticks) { close(fds[1]); }
    pthread_join(th, NULL);

    uint32_t lost = ticks - got;
    if (got == 0) { printf("FINAL t=%d frames=0 late=0 lost=%u stalls=0 p50_us=0 p99_us=0 max_us=0\nRESULT FAIL\n", duration_s, lost); return 0; }
    qsort(lat_us, got, sizeof lat_us[0], cmp_u32);
    uint32_t p50 = lat_us[got / 2];
    uint32_t p99 = lat_us[(got * 99) / 100 >= got ? got - 1 : (got * 99) / 100];
    uint32_t mx = lat_us[got - 1];
    uint32_t bad = late + lost;
    uint32_t late_pm = (uint32_t)(((uint64_t)bad * 1000) / ticks);

    printf("FINAL t=%d frames=%u late=%u lost=%u stalls=0 p50_us=%u p99_us=%u max_us=%u\n", duration_s, got, (unsigned)late, lost, p50, p99, mx);
    printf("RESULT %s late_pm=%u tol_pm=%u\n", late_pm <= tol_pm ? "PASS" : "FAIL", late_pm, tol_pm);
    return 0;
}
