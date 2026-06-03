#!/usr/bin/env bash
# List paths useful for a lean commit (git commit --only …).
#
# Usage:
#   scripts/lean-commit.sh              # all changed paths (noise filtered)
#   scripts/lean-commit.sh path/a path/b  # echo args (for scripts/validation)
#
# Agents: prefer paths YOU edited this session; this script does not assign blame.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

filter_noise() {
  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    case "$line" in
      cache/*) continue ;;
      scripts/__pycache__/*) continue ;;
      *.pyc) continue ;;
      changelog.d/*) continue ;;
    esac
    printf '%s\n' "$line"
  done
}

if [[ $# -gt 0 ]]; then
  printf '%s\n' "$@"
  exit 0
fi

{
  git diff --name-only 2>/dev/null || true
  git diff --name-only --cached 2>/dev/null || true
  git ls-files --others --exclude-standard 2>/dev/null || true
} | sort -u | filter_noise
