#!/usr/bin/env bash
# Build (if needed) and start the FinAlly container.
# Usage: ./scripts/start_mac.sh [--build] [--no-browser]
set -euo pipefail

IMAGE_NAME="finally:latest"
CONTAINER_NAME="finally"
VOLUME_NAME="finally-data"
HOST_PORT="${FINALLY_PORT:-8000}"
URL="http://localhost:${HOST_PORT}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${ROOT_DIR}"

BUILD=0
OPEN_BROWSER=1

usage() {
  cat <<'EOF'
Usage: scripts/start_mac.sh [--build] [--no-browser]

  --build       Rebuild the image before starting
  --no-browser  Do not open http://localhost:8000
  -h, --help    Show this help
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --build|-b) BUILD=1 ;;
    --no-browser) OPEN_BROWSER=0 ;;
    -h|--help) usage; exit 0 ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker was not found on PATH." >&2
  echo "Install Docker Desktop (https://www.docker.com/products/docker-desktop/) and try again." >&2
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo "Docker is installed but the daemon is not responding." >&2
  echo "Start Docker Desktop (or the Docker service) and try again." >&2
  exit 1
fi

if [ ! -f .env ]; then
  echo "No .env found - creating one from .env.example."
  cp .env.example .env
  echo "Edit .env to set OPENROUTER_API_KEY (or LLM_MOCK=true for offline use)."
fi

if [ "${BUILD}" -eq 1 ] || ! docker image inspect "${IMAGE_NAME}" >/dev/null 2>&1; then
  echo "Building ${IMAGE_NAME} ..."
  docker build -t "${IMAGE_NAME}" .
fi

# Recreate the container so new flags/env take effect. The data volume is untouched.
if docker container inspect "${CONTAINER_NAME}" >/dev/null 2>&1; then
  echo "Removing existing container ${CONTAINER_NAME} ..."
  docker rm -f "${CONTAINER_NAME}" >/dev/null
fi

echo "Starting ${CONTAINER_NAME} ..."
if ! docker run -d \
  --name "${CONTAINER_NAME}" \
  -v "${VOLUME_NAME}:/app/db" \
  -p "${HOST_PORT}:8000" \
  --env-file .env \
  --restart unless-stopped \
  "${IMAGE_NAME}" >/dev/null; then
  echo "Failed to start ${CONTAINER_NAME}. See the Docker error above." >&2
  exit 1
fi

echo "FinAlly is running at ${URL}"
echo "Logs:   docker logs -f ${CONTAINER_NAME}"
echo "Stop:   ./scripts/stop_mac.sh"

if [ "${OPEN_BROWSER}" -eq 1 ]; then
  if command -v open >/dev/null 2>&1; then
    open "${URL}" >/dev/null 2>&1 || true
  elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "${URL}" >/dev/null 2>&1 || true
  fi
fi
