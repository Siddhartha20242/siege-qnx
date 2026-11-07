/* siegewrap: test a program you cannot change.
 *
 *   siegewrap -d seconds [-P prio] [-p period_ms] [-D deadline_ms] [-T tol_pm] [-x max_ms] -- command [args...]
 *
 * Runs the command at priority prio and, beside it at the same priority, a
 * canary: a periodic task that wakes every period_ms and measures how late it
 * woke, against when it was due. Under CPU starvation or scheduler pressure the
 * canary is delayed the way the program is. It also watches the program: it must
 * still be running at the end, or have exited with status 0.
 *
 * With -x, a program that is meant to finish (a batch job) must exit within max_ms or the run fails:
 * a whole-job deadline, which a starved program misses without any canary noticing.
 *
 * It prints the two lines Siege reads (FINAL and RESULT), so the program needs
 * no changes. What it cannot see: the program's own deadlines, its message
 * queues, or locks it shares with others. It measures the scheduling the program
 * would get, and whether it stays alive, not whether its output was on time.
 */
#include "../pipeline/common.h"
#include <signal.h>
#include <sys/wait.h>

#define MAX_TICKS 65536
static uint32_t lat_us[MAX_TICKS];

static int cmp_u32(const void *a, const void *b)
{
    uint32_t x = *(const uint32_t *)a, y = *(const uint32_t *)b;
    return (x > y) - (x < y);
}

int main(int argc, char **argv)
{
    int duration_s = 5, prio = 10, c;
    uint32_t period_ms = 10, deadline_ms = 5, tol_pm = 20, max_run_ms = 0;
    if (getenv("PIPE_PRIO")) prio = atoi(getenv("PIPE_PRIO"));
    if (getenv("DEADLINE_MS")) deadline_ms = (uint32_t)atoi(getenv("DEADLINE_MS"));
    if (getenv("TOL_PM")) tol_pm = (uint32_t)atoi(getenv("TOL_PM"));

    setvbuf(stdout, NULL, _IOLBF, 0);
    while ((c = getopt(argc, argv, "+d:P:p:D:T:x:")) != -1) {
        if (c == 'd') duration_s = atoi(optarg);
        else if (c == 'P') prio = atoi(optarg);
        else if (c == 'p' && atoi(optarg) > 0) period_ms = (uint32_t)atoi(optarg);
        else if (c == 'D') deadline_ms = (uint32_t)atoi(optarg);
        else if (c == 'T') tol_pm = (uint32_t)atoi(optarg);
        else if (c == 'x') max_run_ms = (uint32_t)atoi(optarg);
    }
    if (optind >= argc) {
        fprintf(stderr, "usage: siegewrap -d seconds [-P prio] [-p ms] [-D ms] [-T pm] -- command [args]\n");
        return 2;
    }
    set_prio(prio);

    pid_t child = fork();
    if (child == 0) {
        execvp(argv[optind], &argv[optind]);
        perror("siegewrap: exec");
        _exit(127);
    }
    if (child < 0) { perror("siegewrap: fork"); return 2; }

    uint64_t period_ns = (uint64_t)period_ms * 1000000ULL;
    uint32_t ticks = (uint32_t)((uint64_t)duration_s * 1000000000ULL / period_ns);
    if (ticks > MAX_TICKS) ticks = MAX_TICKS;
    uint32_t late = 0, done = 0;
    int status = 0, exited = 0, overran = 0;
    uint64_t next = now_ns(), t_child = now_ns();

    for (uint32_t i = 0; i < ticks; i++) {
        next += period_ns;
        struct timespec ts = { .tv_sec = (time_t)(next / 1000000000ULL), .tv_nsec = (long)(next % 1000000000ULL) };
        clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &ts, NULL);
        uint64_t l = now_ns() - next;
        lat_us[done++] = (uint32_t)(l / 1000ULL);
        if (l > (uint64_t)deadline_ms * 1000000ULL) late++;
        if (!exited && waitpid(child, &status, WNOHANG) == child) exited = 1;
        if (!exited && max_run_ms && now_ns() - t_child > (uint64_t)max_run_ms * 1000000ULL) {
            overran = 1;
            kill(child, SIGKILL);
            waitpid(child, &status, 0);
            exited = 1;
        }
    }
    if (!exited) { kill(child, SIGTERM); waitpid(child, &status, 0); }

    int died = exited && !overran && !(WIFEXITED(status) && WEXITSTATUS(status) == 0);
    qsort(lat_us, done, sizeof lat_us[0], cmp_u32);
    uint32_t p50 = done ? lat_us[done / 2] : 0;
    uint32_t p99 = done ? lat_us[(done * 99) / 100 >= done ? done - 1 : (done * 99) / 100] : 0;
    uint32_t mx = done ? lat_us[done - 1] : 0;
    uint32_t late_pm = done ? (uint32_t)(((uint64_t)late * 1000) / done) : 1000;

    printf("FINAL t=%d frames=%u late=%u lost=0 stalls=%d p50_us=%u p99_us=%u max_us=%u\n",
           duration_s, done, late, died, p50, p99, mx);
    printf("WRAP child=%s\n", !exited ? "alive at end" : WIFEXITED(status) ? "exited" : "killed by signal");
    if (exited && WIFEXITED(status)) printf("WRAP child_status=%d\n", WEXITSTATUS(status));
    printf("RESULT %s late_pm=%u tol_pm=%u child_died=%d overran=%d\n", (late_pm <= tol_pm && !died && !overran) ? "PASS" : "FAIL", late_pm, tol_pm, died, overran);
    return 0;
}
