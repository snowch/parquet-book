# Parquet, byte by byte: the commands the book tells you to run.
#
#   make            build the reader, the WebAssembly module, the figures and the site
#   make serve      serve the built site at http://localhost:8000
#   make check      everything CI runs
#
# The Rust reader is the one implementation. The site, the figures and the tests are all views
# of it, so everything below starts by building it.

PYTHON ?= python3
CARGO  ?= cargo
PORT   ?= 8000
SHELL  := /bin/bash
WASM   := target/wasm32-unknown-unknown/release/parquet_lab_wasm.wasm

.DEFAULT_GOAL := all

.PHONY: help
help:  ## Show this list
	@grep -hE '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

.PHONY: all
all: wasm figures site  ## Build everything: reader, WebAssembly, figures, site

# -- setup ---------------------------------------------------------------------------------

.PHONY: install
install:  ## Install the toolchain pieces the build needs
	rustup target add wasm32-unknown-unknown
	$(PYTHON) -m pip install -r requirements.txt -r requirements-dev.txt
	npm install -g "mystmd@$$(node -p "require('./package.json').devDependencies.mystmd")"

# -- the reader ----------------------------------------------------------------------------

.PHONY: wasm
wasm:  ## Compile the reader to WebAssembly for the browser
	$(CARGO) build --release -p parquet-lab-wasm --target wasm32-unknown-unknown

.PHONY: figures
figures:  ## Recompute every generated fragment the chapters include
	$(CARGO) run --quiet -p pqlab -- figures

.PHONY: fixtures
fixtures:  ## Rewrite the Parquet fixtures with the pinned pyarrow (rarely needed)
	$(PYTHON) fixtures/generate.py

# -- the book ------------------------------------------------------------------------------

.PHONY: site
site: wasm  ## Parse the pages with MyST and render the site into _build/html
	./scripts/parse-book.sh
	$(PYTHON) scripts/build-site.py --out _build/html

.PHONY: serve
serve:  ## Serve the built site (run `make` first)
	@echo "  http://localhost:$(PORT)"
	@cd _build/html && $(PYTHON) -m http.server $(PORT)

.PHONY: chapter
chapter:  ## Write skeletons for chapters in tools/outline.py that have no page yet
	$(PYTHON) scripts/new-chapter.py --all

# -- tests ---------------------------------------------------------------------------------

.PHONY: test
test:  ## Run the tests (the reader's problems are skipped, as in CI)
	$(CARGO) test --workspace
	$(PYTHON) -m pytest tests -q

.PHONY: problems
problems:  ## Run the chapter problems. They fail until you solve them; that is the point.
	$(CARGO) test -p exercises -- --ignored

.PHONY: browser-test
browser-test: all  ## Drive the built site in a headless browser and check the experiments
	node tests/browser/smoke.mjs _build/html

.PHONY: check
check:  ## Everything CI runs
	./scripts/ci-check.sh

.PHONY: clean
clean:  ## Remove build output (committed fixtures and figures are kept)
	rm -rf _build target
