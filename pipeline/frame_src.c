/* Synthetic camera: emits a deterministic 32x32 frame every period.
 *
 * A bright 5x5 blob moves along a fixed path over low-level noise from a
 * seeded generator, so every run sees identical input.
 */
#include "common.h"
#include "scene.h"

static int use_scene;                    /* -s: real-photo backgrounds instead of noise */
static uint32_t lcg_state = 0x5EED1234u;

static uint32_t lcg(void)
{
    lcg_state = lcg_state * 1664525u + 1013904223u;
    return lcg_state >> 16;
}

static void make_frame(frame_msg_t *f, uint32_t n)
{
    int bx = 4 + (int)((n * 1) % 24);
    int by = 4 + (int)((n * 2) % 24);

    if (use_scene)
        memcpy(f->px, scene_px[n % SCENE_N], FRAME_W * FRAME_H);
    else
        for (int y = 0; y < FRAME_H; y++)
            for (int x = 0; x < FRAME_W; x++)
                f->px[y * FRAME_W + x] = (uint8_t)(lcg() & 0x0F);

    for (int y = by - 2; y <= by + 2; y++)
        for (int x = bx - 2; x <= bx + 2; x++)
            f->px[y * FRAME_W + x] = 200;

    f->gt_x = (int16_t)bx;
    f->gt_y = (int16_t)by;
}

int main(int argc, char **argv)
{
    int duration_s = 10, prio = 10, c;
    uint64_t period_ns = FRAME_PERIOD_NS;

    while ((c = getopt(argc, argv, "d:P:p:s")) != -1) {
        if (c == 's') use_scene = 1;
        else if (c == 'd') duration_s = atoi(optarg);
        else if (c == 'P') prio = atoi(optarg);
        else if (c == 'p' && atoi(optarg) > 0) period_ns = (uint64_t)atoi(optarg) * 1000000ULL;   /* frame period, ms */
    }
    set_prio_report("frame_src", prio);

    int coid = open_name(DET_NAME, 50);
    if (coid == -1) {
        fprintf(stderr, "frame_src: cannot find %s\n", DET_NAME);
        return 1;
    }

    uint32_t total = (uint32_t)(((uint64_t)duration_s * 1000000000ULL) / period_ns);   /* multiply first: dividing first lost frames at -p 30 */
    uint32_t sent = 0, dropped = 0;
    frame_msg_t f;
    uint8_t reply;

    f.type = MSG_FRAME;
    f.pad = 0;

    uint64_t next = now_ns();
    for (uint32_t n = 0; n < total; n++) {
        next += period_ns;
        struct timespec ts = { .tv_sec = (time_t)(next / 1000000000ULL),
                               .tv_nsec = (long)(next % 1000000000ULL) };
        clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &ts, NULL);

        make_frame(&f, n);
        f.seq = n;
        /* Stamp the instant the frame was due, not when we got to run, so a
         * starved camera shows up as latency instead of hiding itself. */
        f.t_capture_ns = next;

        /* The detector may die and be restarted under a new channel. Reconnect
         * by name, without waiting, and count frames sent into the gap. */
        if (coid == -1) coid = name_open(DET_NAME, 0);
        if (coid == -1) { dropped++; continue; }

        timeout_send_reply(IPC_TIMEOUT_NS);
        if (MsgSend(coid, &f, sizeof f, &reply, sizeof reply) == -1) {
            dropped++;
            if (errno != ETIMEDOUT) { name_close(coid); coid = -1; }
        } else {
            sent++;
        }
    }

    /* Tell the detector (and through it the controller) we are done. */
    uint16_t stop = MSG_STOP;
    timeout_send_reply(1000000000ULL);
    MsgSend(coid, &stop, sizeof stop, &reply, sizeof reply);

    printf("SRC frames=%u sent=%u dropped=%u\n", total, sent, dropped);
    return 0;
}
