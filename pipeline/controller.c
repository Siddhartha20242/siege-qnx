/* Controller: turns detections into a steering command and checks deadlines.
 *
 * For every detection it measures capture -> command latency. A frame is a
 * deadline failure if it is late (> deadline) or never arrives (sequence gap
 * without a long outage). A silence longer than OUTAGE_NS is reported as an
 * outage together with its length, which is the recovery time when a service
 * dies and is restarted.
 *
 * Output: one SUMMARY line per second, OUTAGE lines, then FINAL and RESULT.
 * Each SUMMARY is also sent to the /dev/siege resource manager when present.
 */
#include "common.h"
#include <math.h>
#include "monitor.h"

#define MAX_SAMPLES 65536
#define OUTAGE_NS   100000000ULL    /* silence that counts as an outage */
#define ABANDON_NS  3000000000ULL   /* give up if nothing arrives this long */

static uint32_t lat_all[MAX_SAMPLES];
static uint32_t lat_win[MAX_SAMPLES];

static int cmp_u32(const void *a, const void *b)
{
    uint32_t x = *(const uint32_t *)a, y = *(const uint32_t *)b;
    return (x > y) - (x < y);
}

typedef struct {
    uint32_t frames, late, lost, stalls;
} counts_t;

typedef struct {
    uint32_t p50, p99, mx;
} pct_t;

static pct_t percentiles(uint32_t *lat, uint32_t n)
{
    pct_t p = {0, 0, 0};
    if (n) {
        qsort(lat, n, sizeof lat[0], cmp_u32);
        p.p50 = lat[n / 2];
        p.p99 = lat[(n * 99) / 100 >= n ? n - 1 : (n * 99) / 100];
        p.mx = lat[n - 1];
    }
    return p;
}

static int rm_coid = -1;

/* Best effort: never let a missing or slow status device stall the controller. */
static void send_status(const char *line)
{
    if (rm_coid == -1) return;
    stats_msg_t m;
    uint8_t reply;
    memset(&m, 0, sizeof m);
    m.type = MSG_STATS;
    strncpy(m.text, line, sizeof m.text - 1);
    timeout_send_reply(2000000ULL);
    MsgSend(rm_coid, &m, sizeof m, &reply, sizeof reply);
}

#define MON_SCALE 15.424949f      /* log(1 + 5e6), as in tools/train_monitor.py */
#define MON_PRIO  55              /* above anything Siege runs the pipeline or attackers at */

/* State shared between the controller loop (which fills one summary per second) and the
 * predictor thread (which reads it). The thread runs at a high priority so a CPU hog that
 * starves the controller cannot also silence the alarm: a second the controller never
 * reported stays empty, which the network reads as a silent second. */
static float g_hist[MON_MAX_K + 1][MON_PER_SECOND];
static volatile int g_hist_ready[MON_MAX_K + 1];
static volatile int g_started, g_stop;
static volatile uint64_t g_t0;

static void *monitor_thread(void *arg)
{
    (void)arg;
    set_prio(MON_PRIO);
    uint64_t base_start = now_ns();
    int done[MON_MAX_K + 1] = {0}, alarm = 0;
    while (!g_stop) {
        usleep(20000);
        uint64_t base = g_started ? g_t0 : base_start;
        uint64_t el = now_ns() - base;
        for (int k = 1; k <= MON_MAX_K; k++) {
            if (done[k] || el < (uint64_t)k * 1000000000ULL + 500000000ULL) continue;
            float feat[MON_MAX_K * MON_PER_SECOND], pat[MON_PATTERNS];
            memset(feat, 0, sizeof feat);
            for (int t = 1; t <= k; t++)
                if (g_hist_ready[t]) memcpy(&feat[(t - 1) * MON_PER_SECOND], g_hist[t], sizeof(float) * MON_PER_SECOND);
            float pf = monitor_predict(k, feat, pat);
            int best = 0;
            for (int j = 1; j < MON_PATTERNS; j++) if (pat[j] > pat[best]) best = j;
            done[k] = 1;
            printf("MONITOR k=%d at_ms=%u p_fail=%.3f pattern=%s\n", k, (unsigned)(el / 1000000ULL), pf, mon_pattern_name[best]);
            if (pf >= 0.5f && !alarm) {
                alarm = 1;
                printf("MONITOR ALARM k=%d at_ms=%u pattern=%s\n", k, (unsigned)(el / 1000000ULL), mon_pattern_name[best]);
            }
        }
    }
    return NULL;
}

int main(int argc, char **argv)
{
    int prio = 10, c;
    uint64_t deadline_ns = DEADLINE_NS;
    uint32_t tol_permille = 20;      /* tolerated late+lost frames: 2.0% */
    uint32_t recovery_ms = 500;      /* longest tolerated silence */
    uint32_t acc_pm = 50;            /* tolerated wrong detections, per mille of those checked */

    while ((c = getopt(argc, argv, "P:D:T:R:A:")) != -1) {
        if (c == 'P') prio = atoi(optarg);
        else if (c == 'D') deadline_ns = (uint64_t)atoi(optarg) * 1000000ULL;
        else if (c == 'T') tol_permille = (uint32_t)atoi(optarg);
        else if (c == 'R') recovery_ms = (uint32_t)atoi(optarg);
        else if (c == 'A') acc_pm = (uint32_t)atoi(optarg);
    }
    set_prio_report("controller", prio);
    setvbuf(stdout, NULL, _IOLBF, 0);

    name_attach_t *att = name_attach(NULL, CTL_NAME, 0);
    if (!att) { perror("controller: name_attach"); return 1; }
    rm_coid = name_open(RM_NAME, 0);

    const char *profile = getenv("PROFILE");
    if (!profile) profile = "none";

    counts_t all = {0}, win = {0};
    uint32_t n_all = 0, n_win = 0, secs = 0;
    uint32_t expect = 0, outages = 0, outage_frames = 0, max_gap_ms = 0, checked = 0, wrong = 0;
    int started = 0, abandoned = 0;
    uint64_t t0 = 0, next_report = 0, last = 0;
    int16_t cmd = 0;
    union { uint16_t type; det_msg_t d; } m;
    uint8_t reply = 1;

    /* Optional interference predictor (MONITOR=1): a small trained network reads the first
     * seconds of this run's per-second summaries and predicts the verdict early. It sees
     * only what the controller measures. See tools/train_monitor.py and docs/predictor.md. */
    int mon_on = getenv("MONITOR") && atoi(getenv("MONITOR")) > 0;
    pthread_t mon_tid;
    if (mon_on) pthread_create(&mon_tid, NULL, monitor_thread, NULL);

    for (;;) {
        uint64_t to = STALL_NS;
        TimerTimeout(CLOCK_MONOTONIC, _NTO_TIMEOUT_RECEIVE, NULL, &to, NULL);
        struct _msg_info info;
        int rcvid = MsgReceive(att->chid, &m, sizeof m, &info);

        if (rcvid == -1 && errno == ETIMEDOUT) {
            if (started) {
                all.stalls++; win.stalls++;
                if (now_ns() - last > ABANDON_NS) { abandoned = 1; break; }
            }
            continue;
        }
        if (rcvid <= 0) continue;
        if (info.msglen < (int)sizeof m.type) { MsgError(rcvid, EBADMSG); continue; }

        if (m.type == MSG_STOP) {
            MsgReply(rcvid, 0, &reply, 1);
            break;
        }
        MsgReply(rcvid, 0, &reply, 1);
        if (m.type != MSG_DET) {
            /* Stray messages must not keep a dead pipeline alive: the give-up check used to run only
             * when a receive timed out, so a process sending every 100 ms postponed it for ever. */
            if (started && now_ns() - last > ABANDON_NS) { abandoned = 1; break; }
            continue;
        }
        if (info.msglen < (int)sizeof m.d) continue;      /* short MSG_DET: do not read stale fields */

        uint64_t now = now_ns();
        uint64_t gap_ns = started ? now - last : 0;
        if (!started) {
            started = 1;
            t0 = now;
            g_t0 = now;
            g_started = 1;
            next_report = now + 1000000000ULL;
        }
        last = now;
        if ((uint32_t)(gap_ns / 1000000ULL) > max_gap_ms)
            max_gap_ms = (uint32_t)(gap_ns / 1000000ULL);

        /* Frames the pipeline never delivered: a long silence is an outage
         * (recovery time), a short gap is plain loss. */
        if (m.d.seq > expect) {
            uint32_t gap = m.d.seq - expect;
            if (gap_ns > OUTAGE_NS) {
                outages++;
                outage_frames += gap;
                printf("OUTAGE ms=%u frames=%u\n", (unsigned)(gap_ns / 1000000ULL), gap);
            } else {
                all.lost += gap;
                win.lost += gap;
            }
        }
        expect = m.d.seq + 1;

        /* Proportional steering toward the frame centre. */
        cmd = (int16_t)((m.d.x - FRAME_W / 2) * 4);
        (void)cmd;

        /* The trained network's answer is checked against where the object
         * really was, so a pipeline that is on time but wrong still fails. */
        if (m.d.model) {
            checked++;
            if (abs(m.d.x - m.d.gt_x) > 1 || abs(m.d.y - m.d.gt_y) > 1) wrong++;
        }

        uint64_t lat_ns = now - m.d.t_capture_ns;
        uint32_t lat_us = (uint32_t)(lat_ns / 1000ULL);
        all.frames++; win.frames++;
        if (lat_ns > deadline_ns) { all.late++; win.late++; }
        if (n_all < MAX_SAMPLES) lat_all[n_all++] = lat_us;
        if (n_win < MAX_SAMPLES) lat_win[n_win++] = lat_us;

        if (now >= next_report) {
            secs = (uint32_t)((now - t0) / 1000000000ULL);
            pct_t p = percentiles(lat_win, n_win);
            printf("SUMMARY t=%u frames=%u late=%u lost=%u stalls=%u p50_us=%u p99_us=%u max_us=%u\n",
                   secs, win.frames, win.late, win.lost, win.stalls, p.p50, p.p99, p.mx);

            uint32_t wbad = win.late + win.lost;
            uint32_t wtot = win.frames + win.lost;
            const char *state = (wtot && wbad * 1000 <= wtot * tol_permille) ? "GREEN" : "RED";
            char st[240];
            snprintf(st, sizeof st, "state=%s t=%u profile=%s frames=%u late=%u lost=%u p50_us=%u p99_us=%u max_us=%u\n",
                     state, secs, profile, win.frames, win.late, win.lost, p.p50, p.p99, p.mx);
            send_status(st);

            if (mon_on && secs >= 1 && secs <= MON_MAX_K) {
                float *h = g_hist[secs];
                h[0] = 1;
                h[1] = fminf(win.late / 50.0f, 1.0f);
                h[2] = fminf(win.lost / 50.0f, 1.0f);
                h[3] = log1pf((float)p.p50) / MON_SCALE;
                h[4] = log1pf((float)p.p99) / MON_SCALE;
                h[5] = log1pf((float)p.mx) / MON_SCALE;
                g_hist_ready[secs] = 1;
            }
            memset(&win, 0, sizeof win);
            n_win = 0;
            next_report += 1000000000ULL;
        }
    }

    if (mon_on) { g_stop = 1; pthread_join(mon_tid, NULL); }
    secs = started ? (uint32_t)((now_ns() - t0) / 1000000000ULL) : 0;
    pct_t p = percentiles(lat_all, n_all);
    printf("FINAL t=%u frames=%u late=%u lost=%u stalls=%u p50_us=%u p99_us=%u max_us=%u outages=%u outage_frames=%u max_gap_ms=%u abandoned=%d checked=%u wrong=%u\n",
           secs, all.frames, all.late, all.lost, all.stalls, p.p50, p.p99, p.mx,
           outages, outage_frames, max_gap_ms, abandoned, checked, wrong);

    /* Emulation produces rare isolated outliers, so the verdict is a late-frame
     * budget rather than "zero misses": PASS if at most tol_permille of frames
     * were late or lost, no silence exceeded the recovery budget, and the
     * pipeline never went quiet for good. */
    uint32_t total = all.frames + all.lost;
    uint32_t bad = all.late + all.lost;
    uint32_t late_pm = total ? (uint32_t)(((uint64_t)bad * 1000) / total) : 1000;
    int accurate = checked == 0 || wrong * 1000ULL <= (uint64_t)checked * acc_pm;
    int pass = !abandoned && total && late_pm <= tol_permille && max_gap_ms <= recovery_ms && accurate;
    printf("RESULT %s late_pm=%u tol_pm=%u max_gap_ms=%u recovery_ms=%u\n",
           pass ? "PASS" : "FAIL", late_pm, tol_permille, max_gap_ms, recovery_ms);

    char st[240];
    snprintf(st, sizeof st, "state=%s final frames=%u late=%u lost=%u outages=%u max_gap_ms=%u p99_us=%u\n",
             pass ? "GREEN" : "RED", all.frames, all.late, all.lost, outages, max_gap_ms, p.p99);
    send_status(st);
    return 0;
}
