/* Tiny fixed-weight object detector.
 *
 * Applies a 3x3 centre-surround kernel over the frame and reports the
 * strongest response as the object position. Weights are constants, so the
 * output is deterministic. -w repeats the pass to model a heavier network.
 */
#include "common.h"

static const int8_t kernel[9] = { -1, -1, -1,
                                  -1,  8, -1,
                                  -1, -1, -1 };

static void detect(const uint8_t *px, int16_t *bx, int16_t *by, int32_t *best)
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

int main(int argc, char **argv)
{
    int prio = 10, passes = 20, c;

    while ((c = getopt(argc, argv, "P:w:")) != -1) {
        if (c == 'P') prio = atoi(optarg);
        else if (c == 'w') passes = atoi(optarg);
    }
    set_prio_report("detector", prio);

    name_attach_t *att = name_attach(NULL, DET_NAME, 0);
    if (!att) { perror("detector: name_attach"); return 1; }

    int ctl = open_name(CTL_NAME, 50);
    if (ctl == -1) {
        fprintf(stderr, "detector: cannot find %s\n", CTL_NAME);
        return 1;
    }

    frame_msg_t f;
    det_msg_t d;
    uint8_t reply;

    for (;;) {
        int rcvid = MsgReceive(att->chid, &f, sizeof f, NULL);
        if (rcvid <= 0) continue;           /* pulse or error */

        if (f.type == MSG_STOP) {
            MsgReply(rcvid, 0, &reply, 1);
            uint16_t stop = MSG_STOP;
            timeout_send_reply(1000000000ULL);
            MsgSend(ctl, &stop, sizeof stop, &reply, sizeof reply);
            break;
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
        for (int i = 0; i < passes; i++)
            detect(f.px, &d.x, &d.y, &d.score);

        timeout_send_reply(IPC_TIMEOUT_NS);
        MsgSend(ctl, &d, sizeof d, &reply, sizeof reply);
    }
    return 0;
}
