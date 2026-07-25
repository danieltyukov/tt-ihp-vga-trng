# Top level convenience wrapper. Everything here runs inside the repo local
# venv, so no shell activation is needed.
#
#   make venv     create .venv and install test/requirements.txt
#   make test     cocotb regression (this is the one that must pass)
#   make lint     verilator --lint-only -Wall, zero warnings expected
#   make ring     ring oscillator structural testbench, plain Icarus
#   make synth    yosys area report against the real IHP sg13g2 liberty
#   make capture  64 further model-verified frames for the animated images
#   make sta      OpenSTA timing closure across three real IHP corners
#   make harden   LibreLane hardening to GDS, DRC and LVS signoff, layout render
#   make fpga     yosys + nextpnr-ice40 + icepack for an ICE40UP5K
#   make ring-freq ring oscillator frequency from the Liberty delay tables
#   make images   regenerate every PNG and GIF in docs/img from sim output
#   make check    lint + ring + test + synth
#   make clean
#
# sta and harden need an installed ihp-sg13g2 PDK plus openroad, librelane and
# klayout. Override the PDK location with PDK_ROOT_IHP. Everything else works
# with just iverilog, verilator, yosys and the venv.

VENV    := .venv
PY      := $(VENV)/bin/python
PIP     := $(VENV)/bin/pip
VENV_BIN := $(abspath $(VENV))/bin

.PHONY: all venv test lint ring synth capture sta harden fpga ring-freq images check clean

all: check

venv: $(VENV)/.stamp
$(VENV)/.stamp: test/requirements.txt
	python3 -m venv $(VENV)
	$(PIP) install -q --upgrade pip
	$(PIP) install -q -r test/requirements.txt
	touch $@

test: venv
	PATH="$(VENV_BIN):$$PATH" $(MAKE) -C test clean
	PATH="$(VENV_BIN):$$PATH" $(MAKE) -C test
	@! grep -q "<failure" test/results.xml || { echo "TEST FAILURES in results.xml"; exit 1; }
	@echo "cocotb regression: all tests passed"

lint:
	$(MAKE) -C test lint

ring:
	$(MAKE) -C test ring

synth:
	./scripts/synth_report.sh

# Static timing against the real slow, typical and fast IHP corners. Fails if
# setup does not close at the signoff corner, so the clock_hz in info.yaml cannot
# silently stop being true.
sta:
	./scripts/run_sta.sh

# Local GDS hardening with the same LibreLane version the tt gds action pins.
# About 25 minutes. Writes docs/hardening/ and docs/img/layout.png.
harden:
	./scripts/harden.sh

# yosys + nextpnr-ice40 + icepack + icetime for the device Tiny Tapeout's FPGA
# emulator uses. Validates the ice40 flow, not the fpga GitHub workflow.
fpga:
	./scripts/run_fpga.sh

ring-freq:
	python3 scripts/ring_freq.py

capture: venv
	PATH="$(VENV_BIN):$$PATH" $(MAKE) -C test capture

# Needs the per pattern frames from `make test` and the sequences from
# `make capture`. Both are simulation runs and both verify every frame against
# test/model.py, so no image in docs/img is a mockup.
images: venv
	$(PY) scripts/make_images.py

check: lint ring test synth

clean:
	$(MAKE) -C test clean || true
	rm -rf test/sim_build test/results.xml test/output test/__pycache__
	rm -f test/tb.fst test/tb.vcd
