# Tiny Tapeout cocotb test harness.
# See https://docs.cocotb.org/en/stable/quickstart.html for the cocotb side.
#
# Extra targets on top of the stock template:
#   make lint     verilator --lint-only -Wall over every source file
#   make ring     plain Icarus testbench for the ring oscillator path
#   make synth    Yosys area report, writes docs/synth/

SIM ?= icarus
FST ?= -fst
TOPLEVEL_LANG ?= verilog
SRC_DIR = $(CURDIR)/../src
# Keep this list in sync with source_files in ../info.yaml.
PROJECT_SOURCES = \
	tt_um_danieltyukov_vga_trng.v \
	vga_sync.v \
	pattern_mux.v \
	pat_xor.v \
	pat_bars.v \
	pat_sierp.v \
	pat_ripple.v \
	sine_q.v \
	pat_plasma.v \
	pat_ball.v \
	pat_stars.v \
	pat_rule30.v \
	trng.v \
	ring_inv.v \
	ring_gate.v \
	ring_osc.v \
	entropy_source.v \
	von_neumann.v \
	lfsr_whitener.v \
	health_monitor.v

ifneq ($(GATES),yes)

# RTL simulation:
SIM_BUILD = sim_build/rtl
VERILOG_SOURCES += $(addprefix $(SRC_DIR)/,$(PROJECT_SOURCES))
COMPILE_ARGS += -DSIM

else

# Gate level simulation:
SIM_BUILD = sim_build/gl
COMPILE_ARGS += -DGL_TEST
COMPILE_ARGS += -DFUNCTIONAL
COMPILE_ARGS += -DSIM
VERILOG_SOURCES += $(PDK_ROOT)/ihp-sg13g2/libs.ref/sg13g2_io/verilog/sg13g2_io.v
VERILOG_SOURCES += $(PDK_ROOT)/ihp-sg13g2/libs.ref/sg13g2_stdcell/verilog/sg13g2_stdcell.v
# this gets copied in by the GDS action workflow
VERILOG_SOURCES += $(CURDIR)/gate_level_netlist.v

endif

COMPILE_ARGS += -I$(SRC_DIR)

VERILOG_SOURCES += $(CURDIR)/tb.v
TOPLEVEL = tb

COCOTB_TEST_MODULES = test

# cocotb's own rules. Guarded so that lint / ring / synth still work in a shell
# where the venv has not been activated.
COCOTB_MAKEFILES := $(shell cocotb-config --makefiles 2>/dev/null)
ifneq ($(COCOTB_MAKEFILES),)
include $(COCOTB_MAKEFILES)/Makefile.sim
else
$(warning cocotb not on PATH: run "source ../.venv/bin/activate" or use the top level Makefile. Only lint, ring and synth are available.)
endif

# --------------------------------------------------------------------------
# Extra targets. These deliberately do not depend on cocotb's own rules.
# --------------------------------------------------------------------------
.PHONY: lint ring synth images

lint:
	verilator --lint-only -Wall \
		--top-module tt_um_danieltyukov_vga_trng \
		$(addprefix $(SRC_DIR)/,$(PROJECT_SOURCES))
	@echo "verilator lint: clean"

ring: sim_build/ring
	./sim_build/ring

RING_SOURCES = $(SRC_DIR)/ring_inv.v $(SRC_DIR)/ring_gate.v \
               $(SRC_DIR)/ring_osc.v $(SRC_DIR)/entropy_source.v

sim_build/ring: tb_ring.v $(RING_SOURCES)
	@mkdir -p sim_build
	iverilog -g2012 -DSIM -o $@ tb_ring.v $(RING_SOURCES)

synth:
	cd .. && ./scripts/synth_report.sh

images:
	cd .. && ./.venv/bin/python scripts/make_images.py
