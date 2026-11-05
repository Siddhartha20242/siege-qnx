/* sieged: the /dev/siege resource manager.
 *
 * Publishes the pipeline's live status as a file:
 *
 *     cat /dev/siege
 *     state=GREEN t=4 profile=prio frames=50 late=0 lost=0 p50_us=2011 ...
 *
 * The controller pushes its per-second status to this process over native
 * message passing (MSG_STATS); readers get the latest line from the device.
 * One dispatch loop serves both the file I/O and the status messages.
 */
#include "common.h"
#include <sys/iofunc.h>
#include <sys/dispatch.h>
#include <sys/stat.h>

static char status_text[256] = "state=IDLE no data yet\n";
static char read_buf[256];

static resmgr_connect_funcs_t connect_funcs;
static resmgr_io_funcs_t io_funcs;
static iofunc_attr_t attr;

static int io_read(resmgr_context_t *ctp, io_read_t *msg, iofunc_ocb_t *ocb)
{
    int rc = iofunc_read_verify(ctp, msg, ocb, NULL);
    if (rc != EOK) return rc;
    if ((msg->i.xtype & _IO_XTYPE_MASK) != _IO_XTYPE_NONE) return ENOSYS;

    /* Single-threaded server: copy the status so the reply stays stable. */
    strncpy(read_buf, status_text, sizeof read_buf - 1);
    read_buf[sizeof read_buf - 1] = '\0';

    int len = (int)strlen(read_buf);
    int off = (int)ocb->offset;
    int n = len - off;
    if (n < 0) n = 0;
    if (n > (int)msg->i.nbytes) n = (int)msg->i.nbytes;

    _IO_SET_READ_NBYTES(ctp, n);
    if (n > 0) {
        SETIOV(ctp->iov, read_buf + off, n);
        ocb->offset += n;
        return _RESMGR_NPARTS(1);
    }
    return _RESMGR_NPARTS(0);
}

/* A status line arriving from the controller. */
static int on_stats(message_context_t *ctp, int code, unsigned flags, void *handle)
{
    (void)code; (void)flags; (void)handle;
    const stats_msg_t *m = (const stats_msg_t *)ctp->msg;
    strncpy(status_text, m->text, sizeof status_text - 1);
    status_text[sizeof status_text - 1] = '\0';
    MsgReply(ctp->rcvid, EOK, NULL, 0);
    return 0;
}

int main(void)
{
    set_prio(10);
    dispatch_t *dpp = dispatch_create();
    if (!dpp) { perror("sieged: dispatch_create"); return 1; }

    resmgr_attr_t rattr;
    memset(&rattr, 0, sizeof rattr);
    rattr.nparts_max = 1;
    rattr.msg_max_size = 2048;

    iofunc_func_init(_RESMGR_CONNECT_NFUNCS, &connect_funcs, _RESMGR_IO_NFUNCS, &io_funcs);
    io_funcs.read = (int (*)(resmgr_context_t *, io_read_t *, void *))io_read;
    iofunc_attr_init(&attr, S_IFCHR | 0444, NULL, NULL);

    if (resmgr_attach(dpp, &rattr, "/dev/siege", _FTYPE_ANY, 0,
                      &connect_funcs, &io_funcs, &attr) == -1) {
        perror("sieged: resmgr_attach");
        return 1;
    }

    if (!name_attach(dpp, RM_NAME, 0)) {
        perror("sieged: name_attach");
        return 1;
    }

    message_attr_t mattr;
    memset(&mattr, 0, sizeof mattr);
    mattr.nparts_max = 1;
    mattr.msg_max_size = sizeof(stats_msg_t);
    if (message_attach(dpp, &mattr, MSG_STATS, MSG_STATS, on_stats, NULL) == -1) {
        perror("sieged: message_attach");
        return 1;
    }

    dispatch_context_t *ctp = dispatch_context_alloc(dpp);
    for (;;) {
        ctp = dispatch_block(ctp);
        if (!ctp) break;
        dispatch_handler(ctp);
    }
    return 0;
}
