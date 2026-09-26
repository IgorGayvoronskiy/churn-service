# Базовая часть

## 1. Пайплайн для сервиса

Зелёный прогон: [GitHub Actions](https://github.com/IgorGayvoronskiy/churn-service/actions/runs/36132897827)

Страница пакета с образом: [GitHub Packages](https://github.com/IgorGayvoronskiy/churn-service/pkgs/container/churn-service)

## 2. Процесс: ветка и pull request

Ссылка на pull request: [Pull Request #3](https://github.com/IgorGayvoronskiy/churn-service/pull/3)

## 3. Три красных прогона

### 3.1. Конфиг

* Красным стал `job-deploy` на шаге "Сервис".
* Под `churn-service-84d58585d4-p952z` находится в статусе `CrashLoopBackOff`.
* Шаг диагностики напечатал ошибку `FileNotFoundError: No such file or directory: 'artifact/churn_model1.joblib'`.

Причину можно определить по статусу пода `CrashLoopBackOff` и логу приложения. В нём явно указано, что при запуске сервис не смог найти файл модели `artifact/churn_model1.joblib`, поэтому приложение завершилось с ошибкой.

Красный прогон: [GitHub Actions](https://github.com/IgorGayvoronskiy/churn-service/actions/runs/36164215265)

Зелёный прогон: [GitHub Actions](https://github.com/IgorGayvoronskiy/churn-service/actions/runs/36165729275)

### 3.2. Секрет

* Красным стал `job-deploy` на шаге "Сервис".
* Под `churn-service-57485bdd75-7kfzh` находится в статусе `CreateContainerConfigError`.
* Шаг диагностики напечатал ошибку `BadRequest: container "api" in pod "churn-service-57485bdd75-7kfzh" is waiting to start: CreateContainerConfigError`.

Причину можно определить по статусу пода `CreateContainerConfigError` и его конфигурации. В логе видно, что сервис пытается получить переменные из Secret `churn-secrets-bad`, из-за чего контейнер не может корректно создать конфигурацию и запуститься.

Красный прогон: [GitHub Actions](https://github.com/IgorGayvoronskiy/churn-service/actions/runs/36167835868)

Зелёный прогон: [GitHub Actions](https://github.com/IgorGayvoronskiy/churn-service/actions/runs/36169056515)

### 3.3. Ресурсы

* Красным стал `job-deploy` на шаге "Сервис".
* Под `churn-service` отсутствует, так как Deployment не был создан из-за некорректного значения ресурсов. В данном случае лимиты оказались ниже реквестов, поэтому под не создался.
* Шаг диагностики напечатал ошибку `NotFound: deployments.apps "churn-service" not found in namespace "default"`.

Причину можно определить непосредственно по логу шага `kubectl apply`: Kubernetes отклонил Deployment из-за слишком большого значения `memory` в `requests` - `976562500Gi`, которое превышает установленный лимит `512Mi`. В диагностике это подтверждается тем, что Deployment `churn-service` отсутствует.

Красный прогон: [GitHub Actions](https://github.com/IgorGayvoronskiy/churn-service/actions/runs/36169590553)

Зелёный прогон: [GitHub Actions](https://github.com/IgorGayvoronskiy/churn-service/actions/runs/36170064022)

# Вопросы

## 1.

В первом прогоне job `build` выполнялся **56 секунд**, во втором - **19 секунд**. Во втором прогоне из кэша были взяты слои `COPY pyproject.toml uv.lock ./` и `RUN uv sync --frozen --no-dev --no-install-project`, поскольку файлы `pyproject.toml` и `uv.lock` между прогонами не изменились. Остальные слои также использовали кэш, так как во втором прогоне изменялся только `ci.yml` на шаге smoke-тестов, а Dockerfile и файлы, необходимые для сборки образа, остались прежними.

[Первый прогон - 56s](https://github.com/IgorGayvoronskiy/churn-service/actions/runs/36132897827) · [Второй прогон - 19s](https://github.com/IgorGayvoronskiy/churn-service/actions/runs/36164215265)

## 2.

Эти поды относятся к предыдущему ReplicaSet и остаются в кластере во время обновления Deployment. При выкате Kubernetes постепенно создаёт новые поды и удаляет старые, поэтому старые поды могут ещё находиться в `ImagePullBackOff`. Это не мешает успешному rollout, поскольку `kubectl rollout status` ожидает готовности реплик нового, актуального ReplicaSet.

## 3.

Пароль хранится в GitHub Secrets и передаётся в workflow через `${{ secrets.DB_PASSWORD }}`, после чего команда `kubectl create secret generic ... --from-literal=POSTGRES_PASSWORD=$DB_PASSWORD` создаёт Kubernetes Secret. В Deployment этот Secret указывается через `secretRef`, поэтому его значение становится переменной окружения внутри контейнера. Хранить пароль в `configmap.yaml` нельзя, поскольку ConfigMap предназначен для несекретной конфигурации.

## 4.

Если убрать `needs: tests`, job `build` сможет выполняться независимо от результата тестов. Например, тесты могут завершиться с ошибкой, но сборка при этом всё равно создаст и отправит образ в registry, после чего этот образ может быть развёрнут в кластере. В результате в окружение попадёт версия приложения, которая не прошла автоматические тесты.

## 5.

За это отвечает условие `if: github.ref == 'refs/heads/main'` в job `build`, поэтому сборка и последующий deploy выполняются только для `main`. Pull request используется для проверки изменений без побочных действий: достаточно запустить тесты и линтер, а создание и публикацию образа, а также развёртывание выполнять уже после слияния изменений в `main`.

## 6.

`pg_advisory_xact_lock` нужен для последовательного выполнения инициализации базы данных: блокировка действует в рамках транзакции и не позволяет нескольким процессам одновременно выполнять этот участок кода. Без блокировки две реплики `churn-service` при старте на пустой базе могут одновременно вызвать `init()` и попытаться создать одну и ту же таблицу, что приведёт к конфликту. Под репликами здесь имеются в виду несколько одновременно работающих подов `churn-service`.

## 7.

Порядок статусов от более раннего к более позднему следующий:

1. **Pending** - под ещё не назначен на ноду, например, когда запрошенные через `requests` ресурсы невозможно выделить на доступной ноде.
2. **CreateContainerConfigError** - под уже назначен на ноду, но Kubernetes не может подготовить контейнер к запуску, например из-за ссылки на несуществующий Secret.
3. **CrashLoopBackOff** - контейнер уже запускается, но приложение внутри завершается с ошибкой, после чего Kubernetes пытается перезапускать его.

Таким образом, сначала под должен быть запланирован на ноду, затем для него должен быть успешно создан контейнер и только после этого могут возникнуть ошибки непосредственно во время работы приложения.

# Звёздочка 1

## Результаты ускорения пайплайна

| Job    | До (baseline) | После добавления кэша (холодный) | После добавления кэша (тёплый) | Выигрыш                      |
| ------ | ------------: | -------------------------------: | -----------------------------: | ---------------------------- |
| tests  |           35s |                              37s |                            31s | ~11% (35s → 31s)             |
| build  |           26s |                            1m34s |                            19s | ~27% (26s → 19s)             |
| deploy |         1m52s |                            1m50s |                           2m2s | не менялся (в пределах шума) |

**Ссылки на прогоны:** [36170064022](https://github.com/IgorGayvoronskiy/churn-service/actions/runs/36170064022) → [36173404458](https://github.com/IgorGayvoronskiy/churn-service/actions/runs/36173404458) → [36174767146](https://github.com/IgorGayvoronskiy/churn-service/actions/runs/36174767146)

## Что дало выигрыш

**build: 26s → 19s (основной эффект).**

Ускорение дали два независимых рычага, работающих вместе:

* `cache-from: type=gha` / `cache-to: type=gha,mode=max` в `docker/build-push-action` - переиспользование готовых слоёв образа между прогонами GitHub Actions.
* `RUN --mount=type=cache,target=/root/.cache/uv` + `UV_LINK_MODE=copy` в Dockerfile - кэш скачанных uv-пакетов внутри BuildKit-сборки, не требующий повторного скачивания зависимостей с PyPI при пересборке слоя.

Первый прогон с добавлением этих механизмов оказался значительно **медленнее** baseline (1m34s против 26s). Это ожидаемо и объясняется тем, что кэш на этом прогоне ещё не существовал: BuildKit впервые заполнял cache mount и записывал GHA-кэш слоёв. Выигрыш проявился только на следующем прогоне, когда оба кэша уже были прогреты: build упал до 19s - почти вдвое быстрее исходного baseline.

**tests: 35s → 31s (небольшой эффект).**

Ускорение дал `cache-dependency-glob: "uv.lock"` в `setup-uv` - привязка ключа кэша зависимостей к lock-файлу вместо кэширования "по умолчанию", что снижает накладные расходы на восстановление и валидацию кэша `uv sync`. Эффект скромный, так как зависимости в проекте немногочисленные и изначально устанавливались быстро.

**deploy: без изменений (1m52s / 1m50s / 2m2s).**

Ожидаемый результат - ни один из применённых рычагов (кэш uv, кэш слоёв образа) не относится к этому job: время здесь определяется `kubectl rollout status`, ожиданием готовности подов в kind-кластере и `sleep`-паузами в smoke-тестах, что не кэшируется в принципе. Разброс между тремя значениями (1m52s / 1m50s / 2m2s) укладывается в обычные колебания времени старта подов и не является статистически значимым отклонением.

# Звёздочка 2

Красный прогон с расширенной диагностикой: [GitHub Actions](https://github.com/IgorGayvoronskiy/churn-service/actions/runs/36179739220)