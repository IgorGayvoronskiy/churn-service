#!/usr/bin/env bash
# Запуск self-hosted GitHub Actions runner внутри Codespace.
#
# Использование:
#   REPO_URL=<url> RUNNER_TOKEN=<токен> ./scripts/runner-up.sh
#   ./scripts/runner-up.sh                        # REPO_URL и токен можно ввести интерактивно (токен не попадёт в историю)
#   ./scripts/runner-up.sh down                   # остановить и удалить контейнер runner
#
# Запускать ПОСЛЕ создания кластера kind (выполнения скрипта up.sh).

set -euo pipefail

RUNNER_NAME="${RUNNER_NAME:-churn-service-codespace}"
RUNNER_LABELS="${RUNNER_LABELS:-kind-codespace}"
RUNNER_IMAGE="${RUNNER_IMAGE:-ghcr.io/actions/actions-runner:2.337.0}"
CONTAINER="${CONTAINER:-gh-runner-codespace}"
NETWORK="${NETWORK:-kind}"
DOCKER_SOCK="/var/run/docker.sock"

if [ "${1:-}" = "down" ]; then
  docker rm -f "$CONTAINER" >/dev/null 2>&1 && echo "Контейнер $CONTAINER удалён" || echo "Контейнера $CONTAINER нет"
  echo "Если runner остался в статусе Offline, удалите его в Settings -> Actions -> Runners."
  exit 0
fi

if docker inspect "$CONTAINER" >/dev/null 2>&1; then
  if [ "$(docker inspect -f '{{.State.Running}}' "$CONTAINER")" = "true" ]; then
    echo "Runner уже запущен ($CONTAINER)"
  else
    docker start "$CONTAINER" >/dev/null
    echo "Runner запущен ($CONTAINER)"
  fi
  exit 0
fi

if ! docker network inspect "$NETWORK" >/dev/null 2>&1; then
  echo "Docker-сеть '$NETWORK' не найдена. Сначала создайте кластер (scripts/up.sh)." >&2
  exit 1
fi

if [ -z "${REPO_URL:-}" ]; then
  if [ -t 0 ]; then
    read -rp "REPO_URL (например, https://github.com/<логин>/<репозиторий>): " REPO_URL
  fi
fi
if [ -z "${REPO_URL:-}" ]; then
  echo "Не задан REPO_URL. Пример: REPO_URL=https://github.com/<логин>/<репозиторий> $0" >&2
  exit 1
fi

if [ -z "${RUNNER_TOKEN:-}" ]; then
  if [ -t 0 ]; then
    read -rsp "RUNNER_TOKEN: " RUNNER_TOKEN
    echo
  fi
fi
if [ -z "${RUNNER_TOKEN:-}" ]; then
  echo "Не задан RUNNER_TOKEN. Пример: RUNNER_TOKEN=... $0" >&2
  exit 1
fi
export RUNNER_TOKEN REPO_URL RUNNER_NAME RUNNER_LABELS

SOCK_GID="$(stat -c '%g' "$DOCKER_SOCK")"

docker run -d --name "$CONTAINER" \
  --network "$NETWORK" \
  --group-add "$SOCK_GID" \
  --restart unless-stopped \
  -v "$DOCKER_SOCK:$DOCKER_SOCK" \
  -e REPO_URL -e RUNNER_TOKEN -e RUNNER_NAME -e RUNNER_LABELS \
  "$RUNNER_IMAGE" \
  bash -c '[ -f .runner ] || ./config.sh --unattended --url "$REPO_URL" --token "$RUNNER_TOKEN" --name "$RUNNER_NAME" --labels "$RUNNER_LABELS" --replace && ./run.sh' \
  >/dev/null

echo "Runner $RUNNER_NAME запускается, метка: $RUNNER_LABELS"
sleep 8
docker logs --tail 15 "$CONTAINER"