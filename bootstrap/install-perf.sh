#!/usr/bin/env bash
# Deploy the single perf-benchmark skill into a skills directory.
# Run from a checkout of perf-benchmark-skill. Idempotent.
#
#   bootstrap/install-perf.sh --dest <skills-dir>
#   bootstrap/install-perf.sh --harness codex
#   bootstrap/install-perf.sh --harness claude --dest <skills-dir>
#
# --harness selects a default user skills dir (codex: ~/.agents/skills,
# claude: ~/.claude/skills, both: install into each). An explicit --dest
# always wins for that installation. Only runtime files ship: SKILL.md,
# the benchmark/verify/select scripts, useful references, and packaging
# metadata. Tests, history reports, benchmarks, and self-audit scaffolding
# stay in the repo and are never installed.
#
# Existing installs are preserved OUTSIDE the discovery root: a prior
# perf-benchmark tree is moved to a timestamped backup before replacement,
# and a legacy perf-optimization tree is moved aside only when it is
# recognizably ours (a SKILL.md naming perf-optimization); anything else
# is left untouched with a warning. Backups live in a sibling
# "<skills-dir>-backups" directory by default (never inside the skills
# dir, where a backup SKILL.md would be discovered as a second skill), or
# in an explicit --backup-dir, which must also lie outside the skills dir.
set -euo pipefail

usage() {
  echo "usage: install-perf.sh [--dest <skills-dir>] [--harness codex|claude|both] [--backup-dir <dir>] [<dest>]"
}

HARNESS=""
DEST=""
BACKUP_DIR=""
while [ $# -gt 0 ]; do
  case "$1" in
    --dest) DEST="${2:?--dest requires a directory}"; shift 2 ;;
    --harness) HARNESS="${2:?--harness requires codex|claude|both}"; shift 2 ;;
    --backup-dir) BACKUP_DIR="${2:?--backup-dir requires a directory}"; shift 2 ;;
    -h | --help) usage; exit 0 ;;
    --*) echo "unknown option: $1" >&2; usage >&2; exit 2 ;;
    *)
      if [ -z "$DEST" ]; then DEST="$1"; shift; else echo "unexpected arg: $1" >&2; usage >&2; exit 2; fi
      ;;
  esac
done

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

default_dest() {
  case "$1" in
    codex) printf '%s' "$HOME/.agents/skills" ;;
    claude) printf '%s' "$HOME/.claude/skills" ;;
    *) echo "unknown harness: $1 (expected codex|claude|both)" >&2; exit 2 ;;
  esac
}

DESTS=()
if [ -n "$DEST" ]; then
  DESTS+=("$DEST")
elif [ -n "$HARNESS" ]; then
  case "$HARNESS" in
    both) DESTS+=("$(default_dest codex)" "$(default_dest claude)") ;;
    codex | claude) DESTS+=("$(default_dest "$HARNESS")") ;;
    *) echo "unknown harness: $HARNESS (expected codex|claude|both)" >&2; exit 2 ;;
  esac
else
  usage >&2; exit 2
fi

# Runtime payload only (relative to repo root).
PAYLOAD=(
  SKILL.md README.md LICENSE CHANGELOG.md pyproject.toml bootstrap references
  scripts/perf_benchmark_pipeline.py scripts/perf_benchmark
  scripts/profile_discover.py scripts/synth_microbench.py
)

refuse_root() {
  local target="$1"
  local trimmed
  trimmed="$(printf '%s' "$target" | sed 's:/*$::')"
  if [ -z "$trimmed" ]; then
    echo "refusing destination '$target': resolves to filesystem root" >&2
    exit 2
  fi
}

is_managed_legacy() {
  # True when $1 looks like a skill dir this family installed: a SKILL.md
  # whose frontmatter names the expected skill.
  local dir="$1" want="$2"
  [ -f "$dir/SKILL.md" ] && grep -q "^name: $want$" "$dir/SKILL.md" 2>/dev/null
}

trim_trailing_slashes() {
  printf '%s' "$1" | sed 's:/*$::'
}

backup_root_for() {
  # Backup root for a skills dir: explicit --backup-dir wins, otherwise a
  # sibling "<skills-dir>-backups" directory. Never inside the skills dir:
  # a backup tree carries a SKILL.md that discovery would list as a skill.
  if [ -n "$BACKUP_DIR" ]; then
    printf '%s' "$BACKUP_DIR"
  else
    printf '%s-backups' "$(trim_trailing_slashes "$1")"
  fi
}

refuse_backup_inside_dest() {
  local broot="$1" dest="$2"
  local trimmed_broot trimmed_dest
  trimmed_broot="$(trim_trailing_slashes "$broot")"
  trimmed_dest="$(trim_trailing_slashes "$dest")"
  if [ "$trimmed_broot" = "$trimmed_dest" ] || [[ "$trimmed_broot" == "$trimmed_dest"/* ]]; then
    echo "refusing backup dir '$broot': inside skills destination '$dest'" >&2
    exit 2
  fi
}

backup_aside() {
  # Move $1 into backup root $2 as <basename>.bak.<stamp>; print the new path.
  local path="$1" broot="$2"
  local base stamp target
  base="$(basename "$path")"
  mkdir -p "$broot"
  stamp="$(date +%Y%m%dT%H%M%S)-$$"
  target="$broot/${base}.bak.${stamp}"
  while [ -e "$target" ]; do
    stamp="$(date +%Y%m%dT%H%M%S)-$$-$RANDOM"
    target="$broot/${base}.bak.${stamp}"
  done
  echo "  preserving $path -> $target" >&2
  mv "$path" "$target"
  printf '%s' "$target"
}

sweep_stale_backups() {
  # Relocate backups left INSIDE the skills dir by older installers to the
  # backup root (same marker check as live trees; unmanaged names stay put).
  local d="$1" broot="$2"
  local entry base want
  for entry in "$d"/perf-benchmark.bak.* "$d"/perf-optimization.bak.*; do
    [ -e "$entry" ] || continue
    [ -d "$entry" ] || continue
    base="$(basename "$entry")"
    case "$base" in
      perf-benchmark.bak.*) want="perf-benchmark" ;;
      perf-optimization.bak.*) want="perf-optimization" ;;
      *) continue ;;
    esac
    if is_managed_legacy "$entry" "$want"; then
      backup_aside "$entry" "$broot" >/dev/null
    else
      echo "  leaving unmanaged $entry untouched" >&2
    fi
  done
}

install_one() {
  local d="$1"
  local broot backup=""
  refuse_root "$d"
  broot="$(backup_root_for "$d")"
  refuse_root "$broot"
  refuse_backup_inside_dest "$broot" "$d"
  mkdir -p "$d" "$broot"
  sweep_stale_backups "$d" "$broot"
  if [ -e "$d/perf-benchmark" ]; then
    backup="$(backup_aside "$d/perf-benchmark" "$broot")"
  fi
  mkdir -p "$d/perf-benchmark"
  if [ -n "${PERF_INSTALL_INJECT_COPY_FAILURE:-}" ]; then
    echo "  injected copy failure (test hook)" >&2
    rm -rf "$d/perf-benchmark"
    if [ -n "$backup" ]; then
      mv "$backup" "$d/perf-benchmark"
      echo "  restored $backup -> $d/perf-benchmark" >&2
    fi
    return 1
  fi
  if ! (cd "$REPO_ROOT" && cp -r --parents "${PAYLOAD[@]}" "$d/perf-benchmark/"); then
    echo "  copy failed; restoring prior install" >&2
    rm -rf "$d/perf-benchmark"
    if [ -n "$backup" ]; then
      mv "$backup" "$d/perf-benchmark"
      echo "  restored $backup -> $d/perf-benchmark" >&2
    fi
    return 1
  fi
  find "$d/perf-benchmark" \( -name __pycache__ -o -name "*.pyc" \) -exec rm -rf {} +
  if [ -e "$d/perf-optimization" ]; then
    if is_managed_legacy "$d/perf-optimization" "perf-optimization"; then
      backup_aside "$d/perf-optimization" "$broot" >/dev/null
    else
      echo "  leaving unmanaged $d/perf-optimization untouched" >&2
    fi
  fi
  echo "installed perf-benchmark -> $d/perf-benchmark"
}

for d in "${DESTS[@]}"; do
  install_one "$d"
done
