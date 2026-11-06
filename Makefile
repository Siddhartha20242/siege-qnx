# Cross-compile for QNX SDP 8.0, aarch64le. Run inside the VM after
# `source ~/qnx800/qnxsdp-env.sh` (scripts/build.sh does this for you).
CC      = qcc -Vgcc_ntoaarch64le
CFLAGS  = -O2 -Wall -Wextra -std=gnu11
BIN     = build/bin
PROGS   = frame_src detector controller attacker probe supervisor sieged

EXAMPLES = ticker

all: $(addprefix $(BIN)/,$(PROGS) $(EXAMPLES))

$(BIN)/%: pipeline/%.c pipeline/common.h | $(BIN)
	$(CC) $(CFLAGS) -o $@ $<

$(BIN)/ticker: examples/ticker/ticker.c pipeline/common.h | $(BIN)
	$(CC) $(CFLAGS) -o $@ $<

$(BIN):
	mkdir -p $(BIN)

clean:
	rm -rf build

.PHONY: all clean
