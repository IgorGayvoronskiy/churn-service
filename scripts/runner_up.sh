#!/usr/bin/env bash
set -euo pipefail

RUNNER_NAME="${RUNNER_NAME:-churn-service}"
CONTAINER="${CONTAINER:-gh-runner}"
NETWORK="${NETWORK:-kind}"
RUNNER_IMAGE="${RUNNER_IMAGE:-ghcr.io/actions/actions-runner:2.337.0}"
RUNNER_LABELS="${RUNNER_LABELS:-kind}"

# Удаление runner
if [[ "${1:-}" == "down" ]]; then
  if docker rm -f "$CONTAINER" >/dev/null 2>&1; then
    echo "Контейнер '$CONTAINER' удалён."
  else
    echo "Контейнер '$CONTAINER' не найден."
  fi
  exit 0
fi

# Обязательные параметры
if [[ -z "${REPO_URL:-}" ]]; then
  read -rp "GitHub repository URL: " REPO_URL
fi

if [[ -z "${RUNNER_TOKEN:-}" ]]; then
  read -rsp "GitHub runner registration token: " RUNNER_TOKEN
  echo
fi

# Проверка введённых значений
if [[ -z "${REPO_URL//[[:space:]]/}" ]]; then
  echo "Ошибка: GitHub URL не может быть пустым." >&2
  exit 1
fi

if [[ -z "${RUNNER_TOKEN//[[:space:]]/}" ]]; then
  echo "Ошибка: токен не может быть пустым." >&2
  exit 1
fi

if [[ -z "${RUNNER_NAME//[[:space:]]/}" ]]; then
  echo "Ошибка: имя runner не может быть пустым." >&2
  exit 1
fi

# Проверка Docker
if ! docker info >/dev/null 2>&1; then
  echo "Ошибка: Docker Desktop не запущен или недоступен." >&2
  exit 1
fi

# Проверка сети kind
if ! docker network inspect "$NETWORK" >/dev/null 2>&1; then
  echo "Ошибка: Docker-сеть '$NETWORK' не найдена. Сначала создай кластер kind." >&2
  exit 1
fi

# Если контейнер уже существует, не создаём дубликат
if docker inspect "$CONTAINER" >/dev/null 2>&1; then
  echo "Контейнер '$CONTAINER' уже существует."
  echo "Для пересоздания выполни: $0 down"
  exit 1
fi

echo "Запускаю runner '$RUNNER_NAME'..."

docker run -d \
  --name "$CONTAINER" \
  --network "$NETWORK" \
  --group-add 0 \
  --restart unless-stopped \
  -v //var/run/docker.sock:/var/run/docker.sock \
  -e REPO_URL="$REPO_URL" \
  -e RUNNER_TOKEN="$RUNNER_TOKEN" \
  -e RUNNER_NAME="$RUNNER_NAME" \
  -e RUNNER_LABELS="$RUNNER_LABELS" \
  "$RUNNER_IMAGE" \
  bash -c '
    if [ ! -f .runner ]; then
      ./config.sh --unattended \
        --url "$REPO_URL" \
        --token "$RUNNER_TOKEN" \
        --name "$RUNNER_NAME" \
        --labels "$RUNNER_LABELS" \
        --replace || exit $?
    fi
    unset RUNNER_TOKEN
    exec ./run.sh
  ' >/dev/null

echo "Runner запущен."
echo "Имя: $RUNNER_NAME"
echo "Контейнер: $CONTAINER"
echo "Метки: $RUNNER_LABELS"

sleep 3
docker logs --tail 20 "$CONTAINER"
