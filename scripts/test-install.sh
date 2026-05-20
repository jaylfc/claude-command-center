#!/usr/bin/env bash
# Run the clean-install smoke test locally.
#
# Builds tests/install-smoke/Dockerfile against the current working tree.
# The build itself is the test — see the long comment in that Dockerfile.
# Exits 0 on success, non-zero if Docker is missing or any check fails.
#
# Usage:
#   ./scripts/test-install.sh
#
# This is what CI runs (.github/workflows/install-smoke.yml). Keep the two
# in lockstep — anything the workflow needs that's not here is a smell.

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$HERE/.." && pwd)"
DOCKERFILE="$REPO_ROOT/tests/install-smoke/Dockerfile"
IMAGE_TAG="${CCC_INSTALL_SMOKE_TAG:-ccc-install-smoke:local}"

if ! command -v docker >/dev/null 2>&1; then
  cat >&2 <<'EOF'
test-install: docker is not installed or not on PATH.

This script intentionally does NOT auto-install Docker — surprising the user
with a heavyweight install is worse than failing fast. Options:

  - macOS:  install Docker Desktop or `brew install --cask orbstack`
  - Linux:  follow https://docs.docker.com/engine/install/

Then re-run: ./scripts/test-install.sh

(CI runs this on ubuntu-latest, which ships with Docker pre-installed, so
the workflow will still validate every push regardless of local setup.)
EOF
  exit 1
fi

if [ ! -f "$DOCKERFILE" ]; then
  echo "test-install: $DOCKERFILE not found — wrong checkout?" >&2
  exit 1
fi

echo "test-install: building $IMAGE_TAG from $REPO_ROOT"
echo "test-install: dockerfile = $DOCKERFILE"

# Build context is the repo root so the Dockerfile's `COPY . /repo` picks
# up the current working tree (filtered by .dockerignore). --pull keeps the
# base image fresh; --no-cache would be slower with no real benefit since
# the test layer always re-runs (it bundles install + probe in one RUN).
docker build \
  --pull \
  -f "$DOCKERFILE" \
  -t "$IMAGE_TAG" \
  "$REPO_ROOT"

echo "test-install: OK (image: $IMAGE_TAG)"
