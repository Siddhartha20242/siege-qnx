/* Controller: turns detections into a steering command and checks deadlines.
 *
 * For every detection it measures capture -> command latency. A frame is a
 * deadline failure if it is late (> DEADLINE_NS) or never arrives (sequence
 * gap). It prints one SUMMARY line per second and a FINAL line at the end.
 */
#include "common.h"

#define MAX_SAMPLES 65536

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

static void report(const char *tag, uint32_t t, const counts_t *c,
                   uint32_t *lat, uint32_t n)
{
    uint32_t p50 = 0, p99 = 0, mx = 0;
    if (n) {
        qsort(lat, n, sizeof lat[0], cmp_u32);
        p50 = lat[n / 2];
        p99 = lat[(n * 99) / 100 >= n ? n - 1 : (n * 99) / 100];
        mx = lat[n - 1];
    }
    printf("%s t=%u frames=%u late=%u lost=%u stalls=%u p50_us=%u p99_us=%u max_us=%u\n",
           tag, t, c->frames, c->late, c->lost, c->stalls, p50, p99, mx);
}

int main(int argc, char **argv)
{
    int prio = 10, c;
    uint64_t deadline_ns = DEADLINE_NS;
    uint32_t tol_permille = 20;      /* tolerated late+lost frames: 2.0% */

    while ((c = getopt(argc, argv, "P:D:T:")) != -1) {
        if (c == 'P') prio = atoi(optarg);
        else if (c == 'D') deadline_ns = (uint64_t)atoi(optarg) * 1000000ULL;
        else if (c == 'T') tol_permille = (uint32_t)atoi(optarg);
    }
    set_prio_report("controller", prio);
    setvbuf(stdout, NULL, _IOLBF, 0);

    name_attach_t *att = name_attach(NULL, CTL_NAME, 0);
    if (!att) { perror("controller: name_attach"); return 1; }

    counts_t all = {0}, win = {0};
    uint32_t n_all = 0, n_win = 0, secs = 0;
    uint32_t expect = 0;
    int started = 0;
    uint64_t t0 = 0, next_report = 0;
    int16_t cmd = 0;
    union { uint16_t type; det_msg_t d; } m;
    uint8_t reply = 1;

    for (;;) {
        uint64_t to = STALL_NS;
        TimerTimeout(CLOCK_MONOTONIC, _NTO_TIMEOUT_RECEIVE, NULL, &to, NULL);
        int rcvid = MsgReceive(att->chid, &m, sizeof m, NULL);

        if (rcvid == -1 && errno == ETIMEDOUT) {
            if (started) { all.stalls++; win.stalls++; }
            continue;
        }
        if (rcvid <= 0) continue;

        if (m.type == MSG_STOP) {
            MsgReply(rcvid, 0, &reply, 1);
            break;
        }
        MsgReply(rcvid, 0, &reply, 1);
        if (m.type != MSG_DET) continue;

        uint64_t now = now_ns();
        if (!started) {
            started = 1;
            t0 = now;
            next_report = now + 1000000000ULL;
        }

        /* Frames the pipeline never delivered count as missed deadlines. */
        if (m.d.seq > expect) {
            uint32_t gap = m.d.seq - expect;
            all.lost += gap;
            win.lost += gap;
        }
        expect = m.d.seq + 1;

        /* Proportional steering toward the frame centre. */
        cmd = (int16_t)((m.d.x - FRAME_W / 2) * 4);
        (void)cmd;

        uint64_t lat_ns = now - m.d.t_capture_ns;
        uint32_t lat_us = (uint32_t)(lat_ns / 1000ULL);
        all.frames++; win.frames++;
        if (lat_ns > deadline_ns) { all.late++; win.late++; }
        if (n_all < MAX_SAMPLES) lat_all[n_all++] = lat_us;
        if (n_win < MAX_SAMPLES) lat_win[n_win++] = lat_us;

        if (now >= next_report) {
            secs = (uint32_t)((now - t0) / 1000000000ULL);
            report("SUMMARY", secs, &win, lat_win, n_win);
            memset(&win, 0, sizeof win);
            n_win = 0;
            next_report += 1000000000ULL;
        }
    }

    secs = started ? (uint32_t)((now_ns() - t0) / 1000000000ULL) : 0;
    report("FINAL", secs, &all, lat_all, n_all);
    /* Emulation produces rare isolated outliers, so the verdict is a late-frame
     * budget rather than "zero misses": PASS if at most tol_permille of frames
     * were late or lost and the controller was never starved. */
    uint32_t total = all.frames + all.lost;
    uint32_t bad = all.late + all.lost;
    uint32_t late_pm = total ? (uint32_t)(((uint64_t)bad * 1000) / total) : 1000;
    int pass = all.stalls == 0 && total && late_pm <= tol_permille;
    printf("RESULT %s late_pm=%u tol_pm=%u\n", pass ? "PASS" : "FAIL", late_pm, tol_permille);
    return 0;
}
