/* b64cat: print a file as base64 between BEGIN and END markers, so a binary file
 * (a kernel trace, say) can be carried out of a guest that has only a serial console. */
#include <stdio.h>
#include <stdint.h>

static const char tbl[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

int main(int argc, char **argv)
{
    if (argc < 2) { fprintf(stderr, "usage: b64cat file\n"); return 2; }
    FILE *f = fopen(argv[1], "rb");
    if (!f) { perror(argv[1]); return 1; }
    printf("B64BEGIN\n");
    unsigned char in[3];
    size_t n, col = 0;
    while ((n = fread(in, 1, 3, f)) > 0) {
        uint32_t v = (uint32_t)in[0] << 16 | (n > 1 ? (uint32_t)in[1] << 8 : 0) | (n > 2 ? in[2] : 0);
        putchar(tbl[(v >> 18) & 63]);
        putchar(tbl[(v >> 12) & 63]);
        putchar(n > 1 ? tbl[(v >> 6) & 63] : '=');
        putchar(n > 2 ? tbl[v & 63] : '=');
        if ((col += 4) >= 76) { putchar('\n'); col = 0; }
    }
    if (col) putchar('\n');
    printf("B64END\n");
    fclose(f);
    return 0;
}
