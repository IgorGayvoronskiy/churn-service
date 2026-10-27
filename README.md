# О сервисе

Сервис предназначен для прогнозирования оттока пользователей стримингового сервиса на основе их характеристик и поведения. Для каждого пользователя модель оценивает вероятность ухода, что позволяет выявлять клиентов с высоким риском оттока и использовать эти прогнозы для разработки мер по их удержанию. Модель доступна для использования через API, разработанный на FastAPI, а развёртывание и управление сервисом осуществляются в Kubernetes.

В качестве модели машинного обучения используется CatBoost - алгоритм градиентного бустинга над решающими деревьями, подходящий для табличных данных и работы с категориальными признаками. Жизненный цикл модели автоматизирован с помощью Airflow: он включает валидацию данных, переобучение и обновление модели. Эксперименты и версии моделей отслеживаются через MLflow, а версионирование датасетов организовано с помощью DVC и S3-совместимого хранилища RustFS. Для мониторинга состояния сервиса и его метрик используются Prometheus и Grafana, что обеспечивает наблюдаемость и упрощает диагностику проблем в работающей системе.

# Quickstart

1. Сперва вам понадобятся установленные WSL2 и Docker Desktop на вашей машине.

   WSL2 (PowerShell от администратора, затем перезагрузка)

   ```powershell
   wsl --install
   wsl --set-default-version 2
   ```

   Docker Desktop: [https://www.docker.com/products/docker‐desktop/](https://www.docker.com/products/docker-desktop/)  
   при установке оставить галочку "Use WSL 2 instead of Hyper‐V"  
   после запуска: Settings‐> General‐> Use the WSL 2 based engine

2. Далее выполните fork GitHub репозитория <https://github.com/IgorGayvoronskiy/churn-service>
   а затем через PowerShell клонируйте его на своё устройство:

   ```powershell
   git clone https://github.com/<логин>/<название_вашего_репозитория>.git
   cd <название_вашего_репозитория>
   ```

3. Перед настройкой окружения необходимо включить GitHub Actions в форке репозитория.

   1. Откройте свой форк на GitHub и перейдите в **Settings → Actions → General**.
   2. В разделе **Actions permissions** разрешите использование GitHub Actions, выбрав **Allow all actions and reusable workflows**.
   3. Нажмите **Save**, если настройки были изменены.

   После этого GitHub Actions будет доступен для запуска CI/CD workflow проекта.

4. Далее в директории с проектом запустите скрипт для установки зависимостей:

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\preparation.ps1
   ```

   А затем в Git bash в корне репозитория выполните скрипт подъёма платформы:

   ```bash
   S3_KEY=key S3_SECRET=secret "C:\Program Files\Git\bin\bash.exe" platform/up.sh
   ```

5. После того, как все зависимости были успешно установлены, а платформа поднята, скачайте и закэшируйте данные:

   ```bash
   uv run python get_churn_data.py
   uv run dvc add data/netflix_customer_churn.csv
   ```

   Далее настройте s3 хранилище для dvc:

   ```bash
   uv run dvc remote modify --local laptop access_key_id key
   uv run dvc remote modify --local laptop secret_access_key secret
   ```

   Перед первым выполнением `dvc push` убедитесь, что имя хранилища корректно разрешается в вашей среде.

   ```bash
   uv run python -c "import socket; print(socket.gethostbyname('s3.localhost'))"
   ```

   Должно вывести `127.0.0.1`, если вы получили `getaddrinfo failed` откройте PowerShell от имени администратора и выполните:

   ```powershell
   Add-Content -Path "$env:SystemRoot\System32\drivers\etc\hosts" -Value "`n127.0.0.1 s3.localhost s3-console.localhost mlflow.localhost airflow.localhost grafana.localhost churn-service.localhost"

   ipconfig /flushdns
   ```

   Повторите DNS-проверку. Она должна вернуть `127.0.0.1`.

   В Git Bash Попробуйте выполнить
   ```bash
   uv run dvc push
   ```

   Если команда `dvc push` завершается ошибками 499/503 либо выполняется слишком долго, причиной может быть системный прокси, перехватывающий запросы к локальному хранилищу.
   Чтобы проверить это, временно исключите локальные адреса из прокси при запуске команды:

   ```bash
   NO_PROXY="localhost,127.0.0.1,.localhost" uv run dvc push
   ```

   Если проблема исчезнет, задайте переменную `NO_PROXY` постоянно в Windows через PowerShell:

   ```powershell
   setx NO_PROXY "localhost,127.0.0.1,.localhost"
   ```

   Затем откройте новый Git Bash терминал и повторите команду.

6. Следующим шагом нужно запустить обучение модели.
   В Git Bash

   ```bash
   MLFLOW_TRACKING_URI=http://mlflow.localhost uv run python -m churn.train
   ```

   Если вы получили ошибку кодировки, ввёдите следующую комманду в терминале:

   ```bash
   export PYTHONIOENCODING=utf-8
   ```
   и повторите обучение.

7. Теперь мы готовы поднять наш сервис.
   Для этого перейдите в GitHub -> Settings -> Actions -> Runners. Создайте новый self-hosted runner на Linux и сохраните токен, который вы можете найти в поле Configure.

   Далее запустите раннер:

   ```bash
   REPO_URL=https://github.com/<логин>/<название_вашего_репозитория> RUNNER_TOKEN=<токен> ./scripts/runner_up.sh
   ```

   Также перед запуском Workflow перейдите в GitHub -> Settings -> Secrets and variables -> Actions создайте новый секрет репозитория с именем `DB_PASSWORD`.

   Затем перейдите в GitHub Actions и в поле workflows выберите ci. Для запуска workflow нажмите на кнопку Run workflow.

8. Отправим запрос для предсказания в наш сервис:

   ```bash
   curl.exe -X POST "http://churn-service.localhost/v1/predict" -H "Content-Type: application/json" -d "@good.json"
   ```

   Ответ с кодом 200 означает, что сервис успешно работает.

# Адреса интерфейсов

1. churn-service - <http://churn-service.localhost>
2. MLflow - <http://mlflow.localhost>
3. Airflow - <http://airflow.localhost>
4. Grafana - <http://grafana.localhost>
5. s3-console - <http://s3-console.localhost>

# Ручной запуск переобучения

Для этого перейдите в Airflow. Во вкладке Dags выберите `churn_retrain` dag, нажмите кнопку "Запустить" и, выбрав необходимые параметры, запустите обучение.