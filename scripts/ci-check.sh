#!/usr/bin/env bash
# Exactly what CI runs. Run it before pushing: `make check`.
#
# CI invokes this same script, so a laptop and CI cannot drift. Each stage says what it protects,
# because a check nobody understands is a check somebody eventually deletes.
set -euo pipefail
cd "$(dirname "$0")/.."

PY_PATHS=(tools scripts tests fixtures)

echo "== Python tooling: lint and format =="
python3 -m ruff check "${PY_PATHS[@]}"
python3 -m ruff format --check "${PY_PATHS[@]}"

echo "== Rust: format and lint =="
cargo fmt --all --check
cargo clippy --workspace --all-targets --quiet -- -D warnings

echo "== Rust: the reader's tests (the reader's problems are #[ignore]d) =="
# The problems in exercises/ fail until a reader solves them, which is their purpose; a suite
# that went red for an unsolved exercise would train everyone to ignore it. `cargo test` skips
# them and runs the scaffolding tests beside them, which prove each problem is answerable.
cargo test --workspace --quiet

echo "== the fixtures are what the generator writes =="
# The fixtures are committed bytes. This regenerates them with the pinned pyarrow and fails on
# any difference, so the documentation, the manifests and the files cannot disagree.
python3 fixtures/generate.py --check

echo "== the generated fragments are what the reader computes =="
# Every number a chapter prints comes from these. A change to the reader or a fixture that moves
# a number fails here until `make figures` is run and the result committed.
cargo run --quiet -p pqlab -- figures --check

echo "== no measured number is typed into prose =="
python3 scripts/verify-numbers.py

echo "== the reader, compiled for the browser =="
cargo build --release --quiet -p parquet-lab-wasm --target wasm32-unknown-unknown

echo "== MyST parses every page and resolves every reference =="
./scripts/parse-book.sh

echo "== the site renders =="
# The renderer raises on a node type it does not handle, so rendering every page on every push is
# what stops new markup from silently disappearing.
python3 scripts/build-site.py --out _build/html

echo "== every link in the built site resolves =="
python3 scripts/check-built-links.py _build/html

echo "== the book's own tests =="
# Includes tests/test_wasm.py: every call the pages make into the WebAssembly reader, made again
# natively, with identical JSON required.
python3 -m pytest tests -q

echo "== the experiments, driven in a headless browser =="
# Needs Playwright and a Chromium. CI installs both; locally the check runs if they are present.
if node -e "require.resolve('playwright')" >/dev/null 2>&1 \
   || [ -d "$(npm root -g 2>/dev/null)/playwright" ]; then
  node tests/browser/smoke.mjs _build/html
elif [ -n "${CI:-}" ]; then
  echo "ERROR: Playwright is not installed, and CI must not skip the browser checks." >&2
  exit 1
else
  echo "  Playwright not installed; skipping (npm install -g playwright && npx playwright install chromium)"
fi

echo
echo "All checks passed."
