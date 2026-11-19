#!/usr/bin/env bash
# Stop and remove the FinAlly container. The data volume is never removed.
# Usage: ./scripts/stop_mac.sh
set -euo pipefail

CONTAINER_NAME="finally"
VOLUME_NAME="finally-data"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker was not found on PATH; nothing to stop."
  exit 0
fi

if ! docker info >/dev/null 2>&1; then
  echo "Docker is installed but the daemon is not responding; nothing to stop."
  exit 0
fi

if docker container inspect "${CONTAINER_NAME}" >/dev/null 2>&1; then
  echo "Stopping ${CONTAINER_NAME} ..."
  docker stop "${CONTAINER_NAME}" >/dev/null 2>&1 || true
  docker rm "${CONTAINER_NAME}" >/dev/null 2>&1 || true
  echo "FinAlly stopped."
else
  echo "FinAlly is not running (no container named ${CONTAINER_NAME})."
fi

echo "Data volume '${VOLUME_NAME}' was kept."
echo "To delete all portfolio data: docker volume rm ${VOLUME_NAME}"
