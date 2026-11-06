/* Your first QNX-native program: message passing between two threads.
 *
 * QNX is a microkernel. Processes and threads talk by sending messages: a
 * client blocks in MsgSend() until a server answers with MsgReply(). This
 * program runs both sides in one process so you can see it work.
 */
#include <stdio.h>
#include <string.h>
#include <pthread.h>
#include <sys/neutrino.h>
#include <sys/utsname.h>

static int chid;                       /* the server's channel */

static void *server(void *arg)
{
    char buf[64], reply[96];
    (void)arg;

    for (int i = 0; i < 3; i++) {
        int rcvid = MsgReceive(chid, buf, sizeof buf, NULL);   /* wait for a client */
        snprintf(reply, sizeof reply, "server got '%s'", buf);
        MsgReply(rcvid, 0, reply, strlen(reply) + 1);          /* unblock the client */
    }
    return NULL;
}

int main(void)
{
    struct utsname u;
    uname(&u);
    printf("Hello from %s %s on %s\n", u.sysname, u.release, u.machine);

    chid = ChannelCreate(0);
    pthread_t t;
    pthread_create(&t, NULL, server, NULL);

    int coid = ConnectAttach(0, 0, chid, _NTO_SIDE_CHANNEL, 0);  /* connect to our own channel */
    for (int i = 0; i < 3; i++) {
        char msg[32], reply[96];
        snprintf(msg, sizeof msg, "ping %d", i);
        MsgSend(coid, msg, strlen(msg) + 1, reply, sizeof reply);  /* blocks until the reply */
        printf("client: %s\n", reply);
    }

    pthread_join(t, NULL);
    return 0;
}
