#!/usr/bin/env bash
set -euo pipefail

KIND_VERSION="${KIND_VERSION:-v0.33.0}"
ARCH="$(dpkg --print-architecture)"   # amd64 или arm64

# Образы, которые up.sh кладёт в узел kind (держите список в синхроне с up.sh)
IMAGES=(
  "apache/airflow:3.3.2"
  "ghcr.io/mlflow/mlflow:v3.16.1"
  "rustfs/rustfs:1.0.0"
)

echo "== kind $KIND_VERSION"
if ! command -v kind >/dev/null 2>&1 || ! kind version | grep -q "$KIND_VERSION"; then
  curl -fsSLo /tmp/kind "https://kind.sigs.k8s.io/dl/${KIND_VERSION}/kind-linux-${ARCH}"
  sudo install -m 0755 /tmp/kind /usr/local/bin/kind
  rm -f /tmp/kind
fi
kind version

echo "== uv"
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh \
    | sudo env UV_INSTALL_DIR=/usr/local/bin UV_NO_MODIFY_PATH=1 sh
fi
uv --version

echo "== зависимости проекта"
if [ -f pyproject.toml ]; then
  uv sync || echo "WARN: uv sync не удался, запустите вручную"
fi

echo "== лимиты inotify (kind + Prometheus/Airflow иначе могут падать с 'too many open files')"
sudo sysctl -w fs.inotify.max_user_watches=524288 fs.inotify.max_user_instances=512 || true

echo "== helm-репозитории"
helm repo add traefik https://traefik.github.io/charts --force-update >/dev/null
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts --force-update >/dev/null
helm repo update >/dev/null

echo "== ждём Docker daemon"
for _ in $(seq 1 30); do
  docker info >/dev/null 2>&1 && break
  sleep 2
done

echo "== предзагрузка образов (up.sh загрузит в kind только те, что уже скачаны)"
for img in "${IMAGES[@]}"; do
  docker pull "$img" || echo "WARN: не удалось скачать $img"
done

echo "== версии"
git --version
docker --version
kubectl version --client
helm version --short