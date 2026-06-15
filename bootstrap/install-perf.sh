#!/usr/bin/env bash
# Deploy perf-benchmark (repo root) + perf-optimization (subdir) into <dest>.
# Run from a checkout of perf-benchmark-skill. Idempotent.
set -euo pipefail
DEST="${1:?usage: install-perf.sh <dest-skills-dir>}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

mkdir -p "$DEST"
# perf-benchmark = whole repo tree (matches current deployed layout, which
# includes the nested perf-optimization/ copy).
rm -rf "$DEST/perf-benchmark"
mkdir -p "$DEST/perf-benchmark"
git -C "$REPO_ROOT" archive HEAD | tar -x -C "$DEST/perf-benchmark"

# perf-optimization = the subdir, deployed as its own skill dir.
rm -rf "$DEST/perf-optimization"
mkdir -p "$DEST/perf-optimization"
git -C "$REPO_ROOT" archive HEAD:perf-optimization | tar -x -C "$DEST/perf-optimization"

echo "installed perf-benchmark + perf-optimization -> $DEST"
