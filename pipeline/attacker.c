/* Siege attackers: five ways a misbehaving neighbour can hurt a real-time
 * pipeline. One binary, one mode per run.
 *
 *   attacker -m cpu   [-n threads] [-a cpumask]  busy-loop threads that never block
 *   attacker -m mem   [-n megabytes] allocate and keep touching memory
 *   attacker -m flood [-n threads]   hammer the detector with junk messages
 *   attacker -m workflood [-n n]     send the detector requests that cost real CPU
 *   attacker -m fd    [-n unused]    exhaust fds, channels and connections
 *   attacker -m crash                spawn a child that crashes, forever
 *
 * Common: -d seconds (default 10), -P priority (default 10),
 *         -s budget_ms:period_ms  cap the attacker with SCHED_SPORADIC.
 */
#include "common.h"
#include <fcntl.h>
#include <process.h>
#include <sys/wait.h>

static uint64_t g_end_ns;
static int g_prio = 10;
static unsigned long g_mask;      /* optional CPU run mask for hog threads */
static long g_ss_budget_ms, g_ss_period_ms;   /* SCHED_SPORADIC budget, 0 = off */

/* Set this thread's scheduling: plain round-robin, or a sporadic server that
 * caps the thread at budget_ms of CPU per period_ms, then drops it to a low
 * priority until the budget is replenished. */
static int atk_set_prio(void)
{
    if (!g_ss_period_ms) return set_prio(g_prio);

    struct sched_param sp;
    memset(&sp, 0, sizeof sp);
    sp.sched_priority = g_prio;
    sp.sched_ss_low_priority = 2;
    sp.sched_ss_max_repl = 4;
    sp.sched_ss_repl_period.tv_sec  = g_ss_period_ms / 1000;
    sp.sched_ss_repl_period.tv_nsec = (g_ss_period_ms % 1000) * 1000000L;
    sp.sched_ss_init_budget.tv_sec  = g_ss_budget_ms / 1000;
    sp.sched_ss_init_budget.tv_nsec = (g_ss_budget_ms % 1000) * 1000000L;
    return pthread_setschedparam(pthread_self(), SCHED_SPORADIC, &sp);
}

static int running(void) { return now_ns() < g_end_ns; }

/* ---- cpu: spin without ever blocking ---------------------------------- */

static volatile uint64_t sink;
static volatile uint32_t cpu_ms[16];
static volatile int cpu_slot;

static void *cpu_thread(void *arg)
{
    (void)arg;
    int slot = __sync_fetch_and_add(&cpu_slot, 1);
    if (g_mask) ThreadCtl(_NTO_TCTL_RUNMASK, (void *)(uintptr_t)g_mask);
    int rc = atk_set_prio();
    uint64_t x = 1;
    while (running())
        for (int i = 0; i < 100000; i++) x = x * 6364136223846793005ULL + 1442695040888963407ULL;
    sink = x;

    struct timespec ts;
    clock_gettime(CLOCK_THREAD_CPUTIME_ID, &ts);
    cpu_ms[slot & 15] = (uint32_t)(ts.tv_sec * 1000 + ts.tv_nsec / 1000000) + (rc ? 1000000 : 0);
    return NULL;
}

static void run_threads(void *(*fn)(void *), int n)
{
    pthread_t t[16];
    int started = 0;
    if (n > 16) n = 16;
    for (int i = 0; i < n; i++) {
        int rc = pthread_create(&t[started], NULL, fn, NULL);
        if (rc) fprintf(stderr, "attacker: pthread_create: %s\n", strerror(rc));
        else started++;
    }
    for (int i = 0; i < started; i++) pthread_join(t[i], NULL);
}

static int mode_cpu(int n)
{
    run_threads(cpu_thread, n);
    printf("ATK mode=cpu threads=%d cpu_ms=", n);
    for (int i = 0; i < n && i < 16; i++) printf("%s%u", i ? "," : "", cpu_ms[i]);
    printf("\n");
    return 0;
}

/* ---- mem: grab memory and keep it hot --------------------------------- */

static int mode_mem(int mb)
{
    enum { CHUNK = 1 << 20 };
    char *blocks[2048];
    int got = 0;

    atk_set_prio();
    while (got < mb && got < 2048) {
        char *p = malloc(CHUNK);
        if (!p) break;
        memset(p, 0xA5, CHUNK);
        blocks[got++] = p;
    }
    while (running())
        for (int i = 0; i < got && running(); i++)
            for (size_t o = 0; o < CHUNK; o += 4096) blocks[i][o]++;
    printf("ATK mode=mem requested_mb=%d held_mb=%d\n", mb, got);
    return 0;
}

/* ---- flood: queue junk messages at the detector ----------------------- */

static volatile uint32_t flood_sent, flood_rejected, flood_timeout;
static uint16_t flood_type = MSG_JUNK;
static volatile int flood_errno, first_errno;
static volatile uint32_t first_fail_at, flood_reconnects;

static void *flood_thread(void *arg)
{
    (void)arg;
    atk_set_prio();
    int coid = open_name(DET_NAME, 50);
    if (coid == -1) return NULL;

    frame_msg_t junk;
    memset(&junk, 0x55, sizeof junk);
    junk.type = flood_type;
    junk.seq = flood_type == MSG_WORK ? 150 : 0;   /* passes the detector must run */
    uint8_t reply;

    while (running()) {
        timeout_send_reply(IPC_TIMEOUT_NS);
        flood_sent++;
        if (MsgSend(coid, &junk, sizeof junk, &reply, sizeof reply) == -1) {
            if (errno == ETIMEDOUT) flood_timeout++;
            else {
                if (!first_fail_at) { first_fail_at = flood_sent; first_errno = errno; }
                flood_rejected++; flood_errno = errno;
                if (errno != EINVAL) {          /* connection lost: reconnect */
                    name_close(coid);
                    coid = open_name(DET_NAME, 5);
                    flood_reconnects++;
                    if (coid == -1) return NULL;
                }
            }
        }
    }
    return NULL;
}

static int mode_flood(int n, const char *label)
{
    run_threads(flood_thread, n);
    printf("ATK mode=%s threads=%d sent=%u rejected=%u timed_out=%u last_errno=%d first_fail_at=%u first_errno=%d reconnects=%u\n",
           label, n, flood_sent, flood_rejected, flood_timeout, flood_errno, first_fail_at, first_errno, flood_reconnects);
    return 0;
}

/* ---- fd: exhaust per-process and kernel object tables ----------------- */

static int mode_fd(int unused)
{
    (void)unused;
    atk_set_prio();
    int fds = 0, chans = 0, conns = 0;
    int fd_errno = 0, ch_errno = 0, co_errno = 0;

    while (running()) {
        if (open("/dev/null", O_RDONLY) == -1) { fd_errno = errno; break; }
        fds++;
    }
    int chid = -1;
    while (running() && chans < 200000) {
        int c = ChannelCreate(0);
        if (c == -1) { ch_errno = errno; break; }
        chid = c;
        chans++;
    }
    while (running() && chid != -1 && conns < 200000) {
        if (ConnectAttach(0, 0, chid, _NTO_SIDE_CHANNEL, 0) == -1) { co_errno = errno; break; }
        conns++;
    }
    while (running()) usleep(100000);     /* hold everything until the end */
    printf("ATK mode=fd fds=%d(errno %d) channels=%d(errno %d) connections=%d(errno %d)\n",
           fds, fd_errno, chans, ch_errno, conns, co_errno);
    return 0;
}

/* ---- crash: a service that dies instantly and is restarted instantly -- */

static int crash_child(void)
{
    char *p = malloc(1 << 20);
    if (p) memset(p, 1, 1 << 20);
    volatile int *bad = NULL;
    *bad = 1;                            /* SIGSEGV */
    return 0;
}

static int mode_crash(void)
{
    uint32_t restarts = 0;
    atk_set_prio();
    while (running()) {
        int pid = spawnl(P_NOWAIT, "/proc/boot/attacker", "attacker", "-m", "child", (char *)NULL);
        if (pid == -1) { usleep(1000); continue; }
        int st;
        waitpid(pid, &st, 0);
        restarts++;
    }
    printf("ATK mode=crash restarts=%u\n", restarts);
    return 0;
}

int main(int argc, char **argv)
{
    const char *mode = "cpu";
    int duration_s = 10, n = -1, c;

    setvbuf(stdout, NULL, _IOLBF, 0);
    while ((c = getopt(argc, argv, "m:d:P:n:a:s:")) != -1) {
        switch (c) {
        case 'm': mode = optarg; break;
        case 'd': duration_s = atoi(optarg); break;
        case 'P': g_prio = atoi(optarg); break;
        case 'n': n = atoi(optarg); break;
        case 'a': g_mask = strtoul(optarg, NULL, 0); break;
        case 's': {                       /* -s budget_ms:period_ms */
            char *colon = strchr(optarg, ':');
            if (colon) { g_ss_budget_ms = atol(optarg); g_ss_period_ms = atol(colon + 1); }
            break;
        }
        }
    }
    uint64_t t_start = now_ns();
    g_end_ns = t_start + (uint64_t)duration_s * 1000000000ULL;

    int rc;
    if (!strcmp(mode, "cpu"))        rc = mode_cpu(n < 0 ? 2 : n);
    else if (!strcmp(mode, "mem"))   rc = mode_mem(n < 0 ? 300 : n);
    else if (!strcmp(mode, "flood")) rc = mode_flood(n < 0 ? 2 : n, "flood");
    else if (!strcmp(mode, "workflood")) { flood_type = MSG_WORK; rc = mode_flood(n < 0 ? 2 : n, "workflood"); }
    else if (!strcmp(mode, "fd"))    rc = mode_fd(n);
    else if (!strcmp(mode, "crash")) rc = mode_crash();
    else if (!strcmp(mode, "child")) return crash_child();
    else {
        fprintf(stderr, "attacker: unknown mode '%s'\n", mode);
        return 2;
    }
    printf("ATK mode=%s ran_ms=%u\n", mode, (unsigned)((now_ns() - t_start) / 1000000ULL));
    return rc;
}
