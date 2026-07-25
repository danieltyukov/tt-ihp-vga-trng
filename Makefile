# Top level convenience wrapper. Everything here runs inside the repo local
# venv, so no shell activation is needed.
#
#   make venv     create .venv and install test/requirements.txt
#   make test     cocotb regression (this is the one that must pass)
#   make lint     verilator --lint-only -Wall, zero warnings expected
#   make ring     ring oscillator structural testbench, plain Icarus
#   make synth    yosys area report against the real IHP sg13g2 liberty
#   make images   regenerate every PNG, GIF and SVG in docs/img from sim output
#   make check    lint + ring + test + synth
#   make clean

VENV    := .venv
PY      := $(VENV)/bin/python
PIP     := $(VENV)/bin/pip
VENV_BIN := $(abspath $(VENV))/bin

.PHONY: all venv test lint ring synth images check clean

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

images: venv
	$(PY) scripts/make_images.py

check: lint ring test synth

clean:
	$(MAKE) -C test clean || true
	rm -rf test/sim_build test/results.xml test/output test/__pycache__
	rm -f test/tb.fst test/tb.vcd
