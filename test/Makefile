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
# sg13g2_udp.v, when it exists, has to be read before sg13g2_stdcell.v, which
# instantiates ihp_dff_r, ihp_mux2 and ihp_mux4 from it; without it elaboration
# fails with 154 "Unknown module type" errors. It is a wildcard and not a plain
# path because both PDK layouts are in the wild: the snapshot the gds action pins
# (IHP-Open-PDK cb7daaa) still defines those UDPs inside sg13g2_stdcell.v, and
# naming a file that does not exist is a hard error, while naming one that
# duplicates them would be too. The stock template handles neither case.
STDCELL_V = $(PDK_ROOT)/ihp-sg13g2/libs.ref/sg13g2_stdcell/verilog
VERILOG_SOURCES += $(wildcard $(STDCELL_V)/sg13g2_udp.v)
VERILOG_SOURCES += $(PDK_ROOT)/ihp-sg13g2/libs.ref/sg13g2_io/verilog/sg13g2_io.v
VERILOG_SOURCES += $(STDCELL_V)/sg13g2_stdcell.v
# this gets copied in by the GDS action workflow
VERILOG_SOURCES += $(CURDIR)/gate_level_netlist.v

endif

COMPILE_ARGS += -I$(SRC_DIR)

VERILOG_SOURCES += $(CURDIR)/tb.v
TOPLEVEL = tb

# The gate level run adds test_gl (netlist specific checks: the tie cells, and
# that the ring force in tb.v really did leave the entropy path equivalent to the
# RTL one) and then runs the same regression module against the netlist. test.py
# reads GATES from the environment to trim the two longest tests; see the GL
# section at the top of it for exactly what is trimmed and why.
export GATES
ifneq ($(GATES),yes)
COCOTB_TEST_MODULES = test
else
COCOTB_TEST_MODULES = test_gl,test
endif

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
.PHONY: lint ring synth images capture

# Frame sequence capture for the animated images. Slow on purpose: 64 frames of
# 420000 pixel clocks each. Runs the same lockstep model checks as the
# regression, so it is a test too, just not one worth paying for on every run.
capture:
	$(MAKE) -B COCOTB_TEST_MODULES=capture SIM_BUILD=sim_build/capture \
		COCOTB_RESULTS_FILE=results_capture.xml
	@! grep -q "<failure" results_capture.xml || { echo "CAPTURE FAILURES"; exit 1; }
	@echo "capture: all frames verified against the model"


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
