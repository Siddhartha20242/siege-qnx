# Cross-compile for QNX SDP 8.0. Default aarch64le; `make ARCH=x86_64 BIN=build/x86_64/bin` builds for a PC. Run inside the VM after
# `source ~/qnx800/qnxsdp-env.sh` (scripts/build.sh does this for you).
ARCH    ?= aarch64le
CC      = qcc -Vgcc_nto$(ARCH)
CFLAGS  = -O2 -Wall -Wextra -std=gnu11
BIN     ?= build/bin
PROGS   = frame_src detector controller attacker probe supervisor sieged b64cat siegewrap

EXAMPLES = ticker pipeprobe

all: $(addprefix $(BIN)/,$(PROGS) $(EXAMPLES))

$(BIN)/%: pipeline/%.c pipeline/common.h | $(BIN)
	$(CC) $(CFLAGS) -o $@ $<

$(BIN)/detector: pipeline/model.h

# The controller's predictor uses expf and log1pf.
$(BIN)/controller: pipeline/controller.c pipeline/common.h pipeline/monitor.h | $(BIN)
	$(CC) $(CFLAGS) -o $@ $< -lm

$(BIN)/ticker: examples/ticker/ticker.c pipeline/common.h | $(BIN)
	$(CC) $(CFLAGS) -o $@ $<

$(BIN)/pipeprobe: examples/pipeprobe/pipeprobe.c pipeline/common.h | $(BIN)
	$(CC) $(CFLAGS) -o $@ $<

$(BIN):
	mkdir -p $(BIN)

clean:
	rm -rf build

.PHONY: all clean
