# О сервисе
Сервис предназначен для прогнозирования оттока пользователей стримингового сервиса на основе их характеристик и поведения. Для каждого пользователя модель оценивает вероятность ухода, что позволяет выявлять клиентов с высоким риском оттока и использовать эти прогнозы для разработки мер по их удержанию. Модель доступна для использования через API, разработанный на FastAPI, а развёртывание и управление сервисом осуществляются в Kubernetes.<br>

В качестве модели машинного обучения используется CatBoost - алгоритм градиентного бустинга над решающими деревьями, подходящий для табличных данных и работы с категориальными признаками. Жизненный цикл модели автоматизирован с помощью Airflow: он включает валидацию данных, переобучение и обновление модели. Эксперименты и версии моделей отслеживаются через MLflow, а версионирование датасетов организовано с помощью DVC и S3-совместимого хранилища RustFS. Для мониторинга состояния сервиса и его метрик используются Prometheus и Grafana, что обеспечивает наблюдаемость и упрощает диагностику проблем в работающей системе.

# Quickstart
- Сперва вам понадобятся установленные WSL2 и Docker Desktop на вашей машине.
  WSL2 (PowerShell от администратора, затем перезагрузка)
  ```
  wsl --install
  wsl --set-default-version 2
  ```
  Docker Desktop: https://www.docker.com/products/docker‐desktop/
  при установке оставить галочку "Use WSL 2 instead of Hyper‐V"
  после запуска: Settings‐> General‐> Use the WSL 2 based engine

- Далее выполните fork GitHub репозитория https://github.com/IgorGayvoronskiy/churn-service
  а затем в PowerShell клонируйте его на своё устройство:
  ```
  git clone https://github.com/<GITHUB_USERNAME>/churn-service.git
  cd churn-service
  ```

- Далее в директории с проектом запустите скрипт для установки зависимостей:
  ```
  powershell -ExecutionPolicy Bypass -File .\scripts\preparation.ps1
  ```

  А затем в Git bash выполните скрипт подъёма платформы:
  ```
  S3_KEY=... S3_SECRET=... "C:\Program Files\Git\bin\bash.exe" platform/up.sh
  ```

- После того, как все зависимости были успешно установлены, а платформа поднята, выполните скрипт установки данных:
  ```
  uv run python get_churn_data.py
  ```

  Далее настройте s3 хранилище для dvc:
  ```
  uv run dvc remote modify --local laptop access_key_id <Ваш S3_KEY>
  uv run dvc remote modify --local laptop secret_access_key <Ваш S3_SECRET>
  uv run dvc push
  ```

- Следующим шагом нужно запустить обучение модели:
  ```
  MLFLOW_TRACKING_URI=http://mlflow.localhost uv run python -m churn.train
  ```

- Теперь мы готовы поднять наш сервис. 
  Для этого перейдите в GitHub -> Settings -> Actions -> Runners. Создайте новый self-hosted runner на Linux и сохраните токен, который вы можете найти в поле Configure.

  Далее запустите раннер:
  ```
  REPO_URL=https://github.com/<логин>/churn-service RUNNER_TOKEN=<токен> /scripts/runner-up.sh
  ```

  Также перед запуском Workflow перейдите в GitHub -> Settings -> Secrets and variables -> Actions создайте новый секрет репозитория с именем DB_PASSWORD.

  Затем перейдите в GitHub Actions и в поле workflows выберите ci. Для запуска workflow нажмите на кнопку Run workflow.

- Отправим запрос для предсказания в наш сервис:
  ```
  curl.exe -X POST "http://churn-service.localhost/v1/predict" -H "Content-Type: application/json" -d "@good.json"
  ```
  Ответ с кодом 200 означает, что сервис успешно работает.

# Адреса интерфейсов
1. churn-service - http://churn-service.localhost
2. MLflow - http://mlflow.localhost
3. Airflow - http://airflow.localhost
4. Grafana - http://grafana.localhost
5. s3-console - http://s3-console.localhost

# Ручной запуск переобучения
Для этого перейдите в Airflow. Во вкладке Dags выберите churn_retrain dag, нажмите кнопку "Запустить" и, выбрав необходимые параметры, запустите обучение.