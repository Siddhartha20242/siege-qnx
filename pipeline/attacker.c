/* Siege attackers: five ways a misbehaving neighbour can hurt a real-time
 * pipeline. One binary, one mode per run.
 *
 *   attacker -m cpu   [-n threads] [-a cpumask]  busy-loop threads that never block
 *   attacker -m ai    [-n threads]   inference-like compute bursts (a well-meaning neighbour)
 *   attacker -m mem   [-n megabytes] allocate and keep touching memory
 *   attacker -m flood [-n threads]   hammer the detector with junk messages
 *   attacker -m workflood [-n n] [-r rps] [-w passes]   send the detector requests that cost real CPU;
 *                                    -r paces each thread, -w sets the work per request
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
static int g_rate;                /* -r: requests per second per flood thread, 0 = as fast as possible */
static int g_work = 150;          /* -w: detector passes one workflood request costs */
static unsigned long g_mask;      /* optional CPU run mask for hog threads */
static long g_ss_budget_ms, g_ss_period_ms;   /* SCHED_SPORADIC budget, 0 = off */

/* Set this thread's scheduling: plain round-robin, or a sporadic server that
 * caps the thread at budget_ms of CPU per period_ms, then drops it to a low
 * priority until the budget is replenished. */
static volatile int g_prio_denied;      /* threads whose request for g_prio the kernel refused (security policy) */

static int atk_set_prio_raw(void);
static int atk_set_prio(void)
{
    int rc = atk_set_prio_raw();
    if (rc) g_prio_denied++;
    return rc;
}

static int atk_set_prio_raw(void)
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

/* ---- ai: a well-meaning neighbour running inference-like bursts -------- */

#define AI_N 48
static int8_t ai_a[AI_N * AI_N], ai_b[AI_N * AI_N];
static volatile int32_t ai_sink;
static volatile uint32_t ai_bursts;

/* One 48x48 integer matrix multiply, the core of a neural-network layer. */
static void ai_matmul(void)
{
    int32_t acc = 0;
    for (int i = 0; i < AI_N; i++)
        for (int j = 0; j < AI_N; j++) {
            int32_t s = 0;
            for (int k = 0; k < AI_N; k++)
                s += ai_a[i * AI_N + k] * ((volatile int8_t *)ai_b)[k * AI_N + j];
            acc += s;
        }
    ai_sink = acc;
}

/* Compute for 40 ms, rest for the remaining 60 ms of each 100 ms period, like
 * an assistant answering requests. Nothing here is hostile: the damage comes
 * from where it is scheduled. */
static void *ai_thread(void *arg)
{
    (void)arg;
    atk_set_prio();
    for (int i = 0; i < AI_N * AI_N; i++) {
        ai_a[i] = (int8_t)(i * 7);
        ai_b[i] = (int8_t)(i * 13);
    }
    const uint64_t burst_ns = 40000000ULL, period_ns = 100000000ULL;
    while (running()) {
        uint64_t t0 = now_ns();
        while (now_ns() - t0 < burst_ns && running()) ai_matmul();
        ai_bursts++;
        uint64_t used = now_ns() - t0;
        if (used < period_ns) usleep((useconds_t)((period_ns - used) / 1000));
    }
    return NULL;
}

static int mode_ai(int n)
{
    run_threads(ai_thread, n);
    printf("ATK mode=ai threads=%d bursts=%u\n", n, ai_bursts);
    return 0;
}

/* ---- pinv: priority inversion through a shared lock -------------------- */

/* The classic setup. A low-priority holder takes a lock the pipeline needs
 * and works while holding it; medium-priority hogs, above the holder and
 * below the pipeline, keep it from running. With a plain mutex the pipeline
 * waits behind the holder for as long as the hogs run. With a priority-
 * inheriting mutex the holder is lifted to the waiter's priority and finishes.
 *   PINV=none      PTHREAD_PRIO_NONE (the unsafe choice)
 *   PINV=inherit   PTHREAD_PRIO_INHERIT
 *   PINV unset     the system default */
static shared_lock_t *pinv_lock;
static volatile int pinv_ready;

/* The holder takes the lock first, at the high priority it inherited from the
 * process that created it, and only then drops to a low priority and starts
 * working under the lock. If it were starved before taking the lock there would
 * be nothing to invert. */
static void *pinv_holder(void *arg)
{
    (void)arg;
    pthread_mutex_lock(&pinv_lock->m);
    struct sched_param sp = { .sched_priority = g_prio > 4 ? g_prio - 3 : 1 };
    pthread_setschedparam(pthread_self(), SCHED_RR, &sp);
    pinv_ready = 1;
    while (running()) {
        uint64_t t0 = now_ns();
        while (now_ns() - t0 < 3000000ULL && running()) sink++;     /* 3 ms of work under the lock */
        pthread_mutex_unlock(&pinv_lock->m);
        usleep(2000);
        pthread_mutex_lock(&pinv_lock->m);
    }
    pthread_mutex_unlock(&pinv_lock->m);
    return NULL;
}

static void *pinv_hog(void *arg)
{
    (void)arg;
    set_prio(g_prio);
    uint64_t x = 1;
    while (running())
        for (int i = 0; i < 100000; i++) x = x * 6364136223846793005ULL + 1442695040888963407ULL;
    sink = x;
    return NULL;
}

static int mode_pinv(void)
{
    const char *proto = getenv("PINV") ? getenv("PINV") : "default";

    shm_unlink(LOCK_SHM);
    int fd = shm_open(LOCK_SHM, O_CREAT | O_EXCL | O_RDWR, 0666);
    if (fd == -1 || ftruncate(fd, sizeof(shared_lock_t)) == -1) { perror("attacker: shared lock"); return 1; }
    pinv_lock = mmap(NULL, sizeof *pinv_lock, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
    close(fd);
    if (pinv_lock == MAP_FAILED) { perror("attacker: mmap"); return 1; }

    pthread_mutexattr_t a;
    pthread_mutexattr_init(&a);
    pthread_mutexattr_setpshared(&a, PTHREAD_PROCESS_SHARED);
    if (!strcmp(proto, "none"))    pthread_mutexattr_setprotocol(&a, PTHREAD_PRIO_NONE);
    if (!strcmp(proto, "inherit")) pthread_mutexattr_setprotocol(&a, PTHREAD_PRIO_INHERIT);
    pthread_mutex_init(&pinv_lock->m, &a);
    pinv_lock->ready = 1;

    /* Hogs first, so both CPUs are already saturated at the medium priority when
     * the holder takes the lock. The holder starts at this process's high
     * priority, takes the lock, drops to its low priority, and is preempted at
     * once while still holding it. */
    pthread_t th[4];
    for (int i = 1; i < 4; i++)                            /* three hogs: more than there are CPUs */
        pthread_create(&th[i], NULL, pinv_hog, NULL);
    usleep(30000);
    pthread_create(&th[0], NULL, pinv_holder, NULL);
    for (int i = 0; i < 4; i++) pthread_join(th[i], NULL);

    printf("ATK mode=pinv protocol=%s lock_taken=%u\n", proto, pinv_lock->counter);
    shm_unlink(LOCK_SHM);
    return 0;
}

/* ---- pipeflood: hammer QNX's pipe manager --------------------------------- */

/* Pipes are served by the `pipe` resource manager, so a pipe write or read is a
 * message to that process. This attacker pushes data through its own pipes as
 * fast as it can, to load the service other programs' pipes depend on. */
static volatile uint64_t pipe_bytes;

static void *pipeflood_thread(void *arg)
{
    (void)arg;
    atk_set_prio();
    int fd[2];
    if (pipe(fd) == -1) return NULL;
    char buf[1024];
    memset(buf, 0x5A, sizeof buf);
    while (running()) {
        if (write(fd[1], buf, sizeof buf) <= 0) break;
        ssize_t n = read(fd[0], buf, sizeof buf);
        if (n <= 0) break;
        pipe_bytes += (uint64_t)n;
    }
    close(fd[0]);
    close(fd[1]);
    return NULL;
}

static int mode_pipeflood(int n)
{
    run_threads(pipeflood_thread, n);
    printf("ATK mode=pipeflood threads=%d bytes=%llu\n", n, (unsigned long long)pipe_bytes);
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

/* ---- membw: stream through a buffer larger than the caches ------------- */

static volatile uint64_t membw_bytes;

static void *membw_thread(void *arg)
{
    (void)arg;
    enum { BUF = 32 << 20 };
    uint64_t *buf = malloc(BUF);
    if (!buf) return NULL;
    memset(buf, 1, BUF);
    atk_set_prio();
    uint64_t sum = 0;
    while (running()) {
        for (size_t i = 0; i < BUF / sizeof *buf; i += 8) { buf[i] += sum; sum += buf[i]; }
        membw_bytes += BUF;
    }
    sink = sum;
    free(buf);
    return NULL;
}

static int mode_membw(int n)
{
    run_threads(membw_thread, n);
    printf("ATK mode=membw threads=%d mb_streamed=%llu\n", n, (unsigned long long)(membw_bytes >> 20));
    return 0;
}

/* ---- timerstorm: a swarm of very short periodic timers ------------------ *
 * Each thread wakes every 100 microseconds, does almost nothing and sleeps
 * again. The CPU it uses is small, but it forces a steady stream of timer
 * interrupts and context switches. This is a user-space stand-in for a noisy
 * interrupt source; a real interrupt storm needs a driver and real hardware. */

static volatile uint64_t timer_wakes;

static void *timerstorm_thread(void *arg)
{
    (void)arg;
    atk_set_prio();
    uint64_t next = now_ns();
    while (running()) {
        next += 100000;
        struct timespec ts = { .tv_sec = (time_t)(next / 1000000000ULL), .tv_nsec = (long)(next % 1000000000ULL) };
        clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &ts, NULL);
        timer_wakes++;
    }
    return NULL;
}

static int mode_timerstorm(int n)
{
    run_threads(timerstorm_thread, n);
    printf("ATK mode=timerstorm threads=%d wakeups=%llu\n", n, (unsigned long long)timer_wakes);
    return 0;
}

/* ---- kcall: a storm of kernel calls ------------------------------------ *
 * Threads that only yield and read the clock, as fast as they can. They never
 * hold a CPU for long but keep entering the kernel and the scheduler. */

static volatile uint64_t kcalls;

static void *kcall_thread(void *arg)
{
    (void)arg;
    atk_set_prio();
    struct timespec ts;
    while (running()) {
        for (int i = 0; i < 1000; i++) { sched_yield(); clock_gettime(CLOCK_MONOTONIC, &ts); }
        kcalls += 2000;
    }
    return NULL;
}

static int mode_kcall(int n)
{
    run_threads(kcall_thread, n);
    printf("ATK mode=kcall threads=%d kernel_calls=%llu\n", n, (unsigned long long)kcalls);
    return 0;
}

/* ---- squat: take the detector's name ----------------------------------- *
 * Registers the pipeline's own service name as soon as it can and then never
 * answers. If the real detector is alive, this shows what QNX does with a second
 * claimant of the same name. If the detector is killed, the supervisor's restart
 * races this process for the name: whoever registers first receives the frames. */

static volatile uint32_t squat_attempts, squat_won, squat_msgs;

static int mode_squat(void)
{
    atk_set_prio();
    name_attach_t *att = NULL;
    union { uint16_t type; char pad[512]; } m;
    uint64_t won_at = 0, first_try = now_ns();
    while (running()) {
        if (!att) {
            squat_attempts++;
            att = name_attach(NULL, DET_NAME, 0);
            if (att) { squat_won = 1; won_at = now_ns(); }
            else usleep(1000);
            continue;
        }
        uint64_t to = 50000000ULL;
        TimerTimeout(CLOCK_MONOTONIC, _NTO_TIMEOUT_RECEIVE, NULL, &to, NULL);
        int rcvid = MsgReceive(att->chid, &m, sizeof m, NULL);
        if (rcvid > 0) squat_msgs++;          /* received, never replied: the sender stays blocked until it times out */
    }
    printf("ATK mode=squat attempts=%u won=%u won_after_ms=%u messages_swallowed=%u\n", squat_attempts, squat_won,
           won_at ? (unsigned)((won_at - first_try) / 1000000ULL) : 0, squat_msgs);
    return 0;
}

/* ---- forge: malformed and forged messages ------------------------------
 *   FORGE=short  messages shorter than the protocol needs, to the detector and the controller. The receivers check the
 *                length (MsgError EBADMSG), so this should change nothing.
 *   FORGE=seq    one well-formed frame carrying a huge sequence number. Nothing in the pipeline authenticates the sender, so the
 *                controller believes it and its loss accounting breaks. A security policy that denies this process the
 *                detector's channel is the QNX answer. Used to test those claims on QNX; see docs/forged-messages.md. */
static volatile uint32_t forge_sent, forge_ok, forge_err;

static int mode_forge(void)
{
    atk_set_prio();
    const char *kind = getenv("FORGE") ? getenv("FORGE") : "short";
    int det = open_name(DET_NAME, 50);
    if (det == -1) { fprintf(stderr, "forge: cannot connect to %s\n", DET_NAME); printf("FORGE kind=%s connect=denied\n", kind); return 1; }
    int ctl = !strcmp(kind, "short") ? open_name(CTL_NAME, 5) : -1;
    uint8_t reply;
    if (!strcmp(kind, "seq")) {
        frame_msg_t f;
        memset(&f, 0, sizeof f);
        f.type = MSG_FRAME;
        f.seq = 0xFFFFFFF0u;
        f.t_capture_ns = now_ns();
        timeout_send_reply(IPC_TIMEOUT_NS);
        forge_sent++;
        if (MsgSend(det, &f, sizeof f, &reply, sizeof reply) == -1) forge_err++; else forge_ok++;
        while (running()) usleep(100000);
    } else {
        uint16_t shortmsg[6];
        while (running()) {
            for (int len = 2; len <= 10; len += 4) {
                shortmsg[0] = MSG_FRAME; shortmsg[1] = 0; shortmsg[2] = 0x7777; shortmsg[3] = 0x7777;
                timeout_send_reply(IPC_TIMEOUT_NS);
                forge_sent++;
                if (MsgSend(det, shortmsg, (size_t)len, &reply, sizeof reply) == -1) forge_err++; else forge_ok++;
                if (ctl != -1) {
                    shortmsg[0] = MSG_DET;
                    timeout_send_reply(IPC_TIMEOUT_NS);
                    forge_sent++;
                    if (MsgSend(ctl, shortmsg, (size_t)len, &reply, sizeof reply) == -1) forge_err++; else forge_ok++;
                }
            }
            usleep(10000);
        }
    }
    printf("FORGE kind=%s sent=%u accepted=%u rejected=%u\n", kind, forge_sent, forge_ok, forge_err);
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
    junk.seq = flood_type == MSG_WORK ? (uint32_t)g_work : 0;   /* passes the detector must run */
    uint8_t reply;

    uint64_t gap_ns = g_rate > 0 ? 1000000000ULL / (uint64_t)g_rate : 0, next = now_ns();
    while (running()) {
        if (gap_ns) {
            next += gap_ns;
            struct timespec ts = { .tv_sec = (time_t)(next / 1000000000ULL), .tv_nsec = (long)(next % 1000000000ULL) };
            clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &ts, NULL);
        }
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
    while ((c = getopt(argc, argv, "m:d:P:n:a:s:r:w:")) != -1) {
        switch (c) {
        case 'm': mode = optarg; break;
        case 'd': duration_s = atoi(optarg); break;
        case 'P': g_prio = atoi(optarg); break;
        case 'n': n = atoi(optarg); break;
        case 'r': g_rate = atoi(optarg); break;
        case 'w': g_work = atoi(optarg); break;
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
    else if (!strcmp(mode, "ai"))    rc = mode_ai(n < 0 ? 2 : n);
    else if (!strcmp(mode, "pinv"))  rc = mode_pinv();
    else if (!strcmp(mode, "pipeflood")) rc = mode_pipeflood(n < 0 ? 2 : n);
    else if (!strcmp(mode, "mem"))   rc = mode_mem(n < 0 ? 300 : n);
    else if (!strcmp(mode, "flood")) rc = mode_flood(n < 0 ? 2 : n, "flood");
    else if (!strcmp(mode, "workflood")) { flood_type = MSG_WORK; rc = mode_flood(n < 0 ? 2 : n, "workflood"); }
    else if (!strcmp(mode, "membw")) rc = mode_membw(n < 0 ? 2 : n);
    else if (!strcmp(mode, "timerstorm")) rc = mode_timerstorm(n < 0 ? 4 : n);
    else if (!strcmp(mode, "kcall")) rc = mode_kcall(n < 0 ? 2 : n);
    else if (!strcmp(mode, "squat")) rc = mode_squat();
    else if (!strcmp(mode, "forge")) rc = mode_forge();
    else if (!strcmp(mode, "fd"))    rc = mode_fd(n);
    else if (!strcmp(mode, "crash")) rc = mode_crash();
    else if (!strcmp(mode, "child")) return crash_child();
    else {
        fprintf(stderr, "attacker: unknown mode '%s'\n", mode);
        return 2;
    }
    printf("ATK mode=%s ran_ms=%u prio_want=%d prio_denied=%d\n", mode, (unsigned)((now_ns() - t_start) / 1000000ULL), g_prio, g_prio_denied);
    return rc;
}
