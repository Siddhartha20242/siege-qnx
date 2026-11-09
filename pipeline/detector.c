/* Object detector, in two flavours (-m filter | -m cnn, or DET_MODEL):
 *
 *   filter  a fixed 3x3 centre-surround kernel; the strongest response is the
 *           object. -w repeats the pass to model a heavier network. (default)
 *   cnn     a small trained convolutional network (pipeline/model.h, produced
 *           by tools/train_detector.py): about 150 thousand multiply-adds per
 *           frame. The controller checks its answers against the camera's
 *           ground truth.
 *
 * Both are deterministic.
 */
#include "common.h"
#include "model.h"

static const int8_t kernel[9] = { -1, -1, -1,
                                  -1,  8, -1,
                                  -1, -1, -1 };

/* px is read through a volatile pointer so repeated passes are real work and
 * cannot be folded into one by the compiler. */
static void detect(const volatile uint8_t *px, int16_t *bx, int16_t *by, int32_t *best)
{
    int32_t top = -1;
    int16_t tx = 0, ty = 0;

    for (int y = 1; y < FRAME_H - 1; y++) {
        for (int x = 1; x < FRAME_W - 1; x++) {
            int32_t acc = 0;
            for (int ky = -1; ky <= 1; ky++)
                for (int kx = -1; kx <= 1; kx++)
                    acc += kernel[(ky + 1) * 3 + (kx + 1)] * px[(y + ky) * FRAME_W + (x + kx)];
            if (acc > top) { top = acc; tx = (int16_t)x; ty = (int16_t)y; }
        }
    }
    *bx = tx; *by = ty; *best = top;
}


/* conv3x3 1->4, ReLU, conv3x3 4->4, ReLU, conv1x1 4->1; the detection is the
 * arg-max of the 28x28 score map, offset by 2 pixels for the two valid
 * convolutions. px is read through a volatile pointer so the work is real. */
static void detect_cnn(const volatile uint8_t *px, int16_t *bx, int16_t *by, int32_t *best)
{
    static float a1[4][30][30], a2[4][28][28];

    for (int oc = 0; oc < 4; oc++)
        for (int y = 0; y < 30; y++)
            for (int x = 0; x < 30; x++) {
                float s = cnn_b1[oc];
                for (int ky = 0; ky < 3; ky++)
                    for (int kx = 0; kx < 3; kx++)
                        s += cnn_w1[oc * 9 + ky * 3 + kx] * ((float)px[(y + ky) * FRAME_W + (x + kx)] * (1.0f / 255.0f));
                a1[oc][y][x] = s > 0.0f ? s : 0.0f;
            }

    for (int oc = 0; oc < 4; oc++)
        for (int y = 0; y < 28; y++)
            for (int x = 0; x < 28; x++) {
                float s = cnn_b2[oc];
                for (int ic = 0; ic < 4; ic++)
                    for (int ky = 0; ky < 3; ky++)
                        for (int kx = 0; kx < 3; kx++)
                            s += cnn_w2[((oc * 4 + ic) * 3 + ky) * 3 + kx] * a1[ic][y + ky][x + kx];
                a2[oc][y][x] = s > 0.0f ? s : 0.0f;
            }

    float top = -1e30f;
    int tx = 0, ty = 0;
    for (int y = 0; y < 28; y++)
        for (int x = 0; x < 28; x++) {
            float s = cnn_b3[0];
            for (int ic = 0; ic < 4; ic++)
                s += cnn_w3[ic] * a2[ic][y][x];
            if (s > top) { top = s; tx = x; ty = y; }
        }
    *bx = (int16_t)(tx + 2);
    *by = (int16_t)(ty + 2);
    *best = (int32_t)(top * 1000.0f);
}

static volatile int32_t work_sink;   /* keeps MSG_WORK compute from being optimised away */

int main(int argc, char **argv)
{
    int prio = 10, passes = 3, c;
    const char *model = getenv("DET_MODEL") ? getenv("DET_MODEL") : "filter";

    while ((c = getopt(argc, argv, "P:w:m:")) != -1) {
        if (c == 'P') prio = atoi(optarg);
        else if (c == 'w') passes = atoi(optarg);
        else if (c == 'm') model = optarg;
    }
    int use_cnn = !strcmp(model, "cnn");
    set_prio_report("detector", prio);

    /* DET_FIXED_PRIO=1: a control experiment. The channel is created with _NTO_CHF_FIXED_PRIORITY, so the thread
     * that receives a message keeps the detector's own priority instead of taking the sender's. Messages are still
     * queued by sender priority. If a flood from priority 30 still breaks the pipeline with this on, the priority
     * boost is not what does the damage. Off by default; see docs/mechanism-control.md. */
    dispatch_t *dpp = NULL;
    if (getenv("DET_FIXED_PRIO") && atoi(getenv("DET_FIXED_PRIO")) > 0) {
        int chid = ChannelCreate(_NTO_CHF_FIXED_PRIORITY | _NTO_CHF_UNBLOCK | _NTO_CHF_DISCONNECT);
        if (chid == -1) { perror("detector: ChannelCreate"); return 1; }
        dpp = dispatch_create_channel(chid, DISPATCH_FLAG_NOLOCK);
        if (!dpp) { perror("detector: dispatch_create_channel"); return 1; }
    }
    name_attach_t *att = name_attach(dpp, DET_NAME, 0);
    if (!att) { perror("detector: name_attach"); return 1; }

    int ctl = open_name(CTL_NAME, 50);
    if (ctl == -1) {
        fprintf(stderr, "detector: cannot find %s\n", CTL_NAME);
        return 1;
    }

    frame_msg_t f;
    det_msg_t d;
    uint8_t reply;
    shared_lock_t *lock = NULL;
    uint32_t frames_seen = 0, lock_count = 0;
    uint64_t lock_wait_max_ns = 0, lock_wait_total_ns = 0;

    for (;;) {
        /* If the camera's STOP is lost (a starved pipeline can drop it), exit on
         * our own after 5 s of silence instead of waiting for ever. */
        uint64_t idle_ns = 5000000000ULL;
        TimerTimeout(CLOCK_MONOTONIC, _NTO_TIMEOUT_RECEIVE, NULL, &idle_ns, NULL);
        struct _msg_info info;
        int rcvid = MsgReceive(att->chid, &f, sizeof f, &info);
        if (rcvid == -1 && errno == ETIMEDOUT && frames_seen > 0) break;
        if (rcvid <= 0) continue;           /* pulse or error */
        /* Never trust the sender's length: a short message would leave the rest of f holding the
         * previous message (or uninitialised stack). STOP is just the type; every other message
         * is a whole frame_msg_t. */
        if (info.msglen < (int)sizeof f.type || (f.type != MSG_STOP && info.msglen < (int)sizeof f)) {
            MsgError(rcvid, EBADMSG);
            continue;
        }

        if (f.type == MSG_STOP) {
            MsgReply(rcvid, 0, &reply, 1);
            struct { uint16_t type, pad; uint32_t total; } stop = { MSG_STOP, 0, info.msglen >= 8 ? f.seq : 0 };
            timeout_send_reply(1000000000ULL);
            MsgSend(ctl, &stop, sizeof stop, &reply, sizeof reply);
            break;
        }

        if (f.type == MSG_WORK) {           /* shared-service abuse: burn CPU, then reply */
            int16_t wx, wy;
            int32_t ws;
            /* The client says how many passes it wants; that is the abuse. */
            uint32_t n = f.seq ? f.seq : (uint32_t)passes;
            if (n > 2000) n = 2000;
            for (uint32_t i = 0; i < n; i++)
                detect(f.px, &wx, &wy, &ws);
            work_sink = ws + wx + wy;
            reply = 1;
            MsgReply(rcvid, 0, &reply, 1);
            continue;
        }

        if (f.type != MSG_FRAME) {          /* junk from a misbehaving client */
            MsgError(rcvid, EINVAL);
            continue;
        }

        /* Release the camera at once; it must not wait on our compute. */
        reply = 1;
        MsgReply(rcvid, 0, &reply, 1);

        d.type = MSG_DET;
        d.pad = 0;
        d.seq = f.seq;
        d.t_capture_ns = f.t_capture_ns;
        d.gt_x = f.gt_x;
        d.gt_y = f.gt_y;
        d.model = (uint8_t)use_cnn;
        if (use_cnn)
            detect_cnn(f.px, &d.x, &d.y, &d.score);
        else
            for (int i = 0; i < passes; i++)
                detect(f.px, &d.x, &d.y, &d.score);

        /* A shared resource (say a calibration table) guarded by a lock that
         * another process may hold. Looked up lazily: it only exists during
         * the priority-inversion scenarios. */
        if (!lock && (frames_seen++ % 10) == 0) lock = open_shared_lock();
        if (lock) {
            uint64_t t_wait = now_ns();
            pthread_mutex_lock(&lock->m);
            uint64_t waited = now_ns() - t_wait;
            lock->counter++;
            pthread_mutex_unlock(&lock->m);
            lock_count++;
            lock_wait_total_ns += waited;
            if (waited > lock_wait_max_ns) lock_wait_max_ns = waited;
        }

        timeout_send_reply(IPC_TIMEOUT_NS);
        MsgSend(ctl, &d, sizeof d, &reply, sizeof reply);
    }
    if (lock_count)
        printf("DET shared lock: taken %u times, longest wait %llu us, total wait %llu us\n", lock_count,
               (unsigned long long)(lock_wait_max_ns / 1000), (unsigned long long)(lock_wait_total_ns / 1000));
    return 0;
}
