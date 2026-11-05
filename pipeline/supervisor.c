/* Supervisor: starts a service, restarts it when it dies, and measures how long
 * each restart takes. Optionally injects faults by killing the service.
 *
 *   supervisor [-P prio] [-k secs] [-n kills] [-r max_restarts] -- cmd [args]
 *
 *   -k secs   SIGKILL the service secs seconds after start (fault injection)
 *   -n kills  how many times to inject, one every secs seconds (default 1)
 *   -r max    restart at most max times; 0 leaves a killed service dead
 *
 * The service counts as ready once its name (DET_NAME) can be opened. Each
 * death-to-ready time is printed as a SUP line.
 */
#include "common.h"
#include <process.h>
#include <signal.h>
#include <sys/wait.h>

/* Wait until the service's name resolves; 0 on success. */
static int wait_ready(void)
{
    uint64_t give_up = now_ns() + 5000000000ULL;
    while (now_ns() < give_up) {
        int c = name_open(DET_NAME, 0);
        if (c != -1) {
            name_close(c);
            return 0;
        }
        usleep(1000);
    }
    return -1;
}

int main(int argc, char **argv)
{
    int prio = 50, kill_every_s = 0, kills_max = 1, restarts_max = 50, c;

    setvbuf(stdout, NULL, _IOLBF, 0);
    while ((c = getopt(argc, argv, "P:k:n:r:")) != -1) {
        switch (c) {
        case 'P': prio = atoi(optarg); break;
        case 'k': kill_every_s = atoi(optarg); break;
        case 'n': kills_max = atoi(optarg); break;
        case 'r': restarts_max = atoi(optarg); break;
        }
    }
    if (optind >= argc) {
        fprintf(stderr, "usage: supervisor [-P prio] [-k secs] [-n kills] [-r max] -- cmd [args]\n");
        return 2;
    }
    set_prio_report("supervisor", prio);

    char **cmd = &argv[optind];
    uint64_t next_kill = kill_every_s ? now_ns() + (uint64_t)kill_every_s * 1000000000ULL : 0;
    int kills = 0, restarts = 0;

    uint64_t t_spawn = now_ns();
    int pid = spawnvp(P_NOWAIT, cmd[0], cmd);
    if (pid == -1) { perror("supervisor: spawn"); return 1; }
    if (wait_ready() == 0)
        printf("SUP service=%s pid=%d start_ms=%u\n", cmd[0], pid,
               (unsigned)((now_ns() - t_spawn) / 1000000ULL));

    for (;;) {
        /* Watch the service until it dies, injecting faults on schedule. */
        int status = 0, died = 0, injected = 0;
        while (!died) {
            if (next_kill && kills < kills_max && now_ns() >= next_kill) {
                kill(pid, SIGKILL);
                kills++;
                injected = 1;
                next_kill += (uint64_t)kill_every_s * 1000000000ULL;
                printf("SUP fault injected: killed %s pid=%d\n", cmd[0], pid);
            }
            if (waitpid(pid, &status, WNOHANG) == pid) died = 1;
            else usleep(1000);
        }
        uint64_t t_death = now_ns();

        if (WIFEXITED(status) && WEXITSTATUS(status) == 0) {
            printf("SUP service finished cleanly, restarts=%d\n", restarts);
            return 0;
        }
        if (restarts >= restarts_max) {
            printf("SUP service died, not restarting (restarts=%d)\n", restarts);
            return 1;
        }

        restarts++;
        pid = spawnvp(P_NOWAIT, cmd[0], cmd);
        if (pid == -1) { perror("supervisor: respawn"); return 1; }
        if (wait_ready() == 0)
            printf("SUP restart=%d death_to_ready_ms=%u injected=%d\n", restarts,
                   (unsigned)((now_ns() - t_death) / 1000000ULL), injected);
        else
            printf("SUP restart=%d never became ready\n", restarts);
    }
}
