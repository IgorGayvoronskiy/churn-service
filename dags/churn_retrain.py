"""Переобучение модели оттока.

train     под с образом сервиса: dvc pull датасета из S3, churn.train, всё в MLflow
promoted  дальше идём, только если гейт в train.py отдал новой версии алиас champion
rollout   перезапуск churn-service: новые поды загрузят нового champion из реестра

Образ для обучения берётся из переменной churn_image, её выставляет CI при каждом деплое.
"""
from datetime import UTC, datetime

from airflow.providers.cncf.kubernetes.operators.pod import KubernetesPodOperator
from airflow.sdk import CronTriggerTimetable, Param, dag, task
from kubernetes.client import models as k8s

PULL = "uv run --no-sync dvc pull -r cluster data/netflix_customer_churn.csv && "
MLFLOW = {"MLFLOW_TRACKING_URI": "http://mlflow.mlops:5000"}

def secret(name: str) -> list:
    return [k8s.V1EnvFromSource(secret_ref=k8s.V1SecretEnvSource(name=name))]


@dag(
    # каждый день в 03:00 по Москве; пропущенные запуски не догоняем, в том числе при снятии с паузы
    schedule=CronTriggerTimetable("0 3 * * *", timezone="Europe/Moscow"),
    catchup=False,
    params={
        "TOTAL_ITERATIONS": Param(
                                1000,
                                type="integer",
                                minimum=1,
                                description="максимум деревьев CatBoost"
                            ),
        "LEARNING_RATE": Param(
                             0.03,
                             type="number",
                             exclusiveMinimum=0,
                             description="скорость обучения"
                         ),
        "DEPTH": Param(6, type="integer", minimum=1, maximum=16, description="глубина деревьев"),
        "EVAL_METRIC": Param(
                           "AUC",
                           type="string",
                           description="метрика на валидации для ранней остановки"
                       ),
        "EARLY_STOPPING_ROUNDS": Param(
                                     100,
                                     type="integer",
                                     minimum=1,
                                     description="сколько итераций ждать улучшения"
                                 ),
    },
    tags=["churn"],
)
def churn_retrain():
    validate = KubernetesPodOperator(
        task_id="validate",
        name="churn-validate",
        namespace="mlops",
        in_cluster=True,
        image="{{ var.value.churn_image }}",
        image_pull_policy="IfNotPresent",
        cmds=["sh", "-c", PULL + "uv run --no-sync python -m churn.data"],
        env_vars=MLFLOW,
        env_from=secret("s3-credentials"),
        get_logs=True,
        on_finish_action="delete_pod",
    )
    train = KubernetesPodOperator(
        task_id="train",
        name="churn-train",
        namespace="mlops",
        in_cluster=True,
        image="{{ var.value.churn_image }}",
        image_pull_policy="IfNotPresent",
        # данных в образе нет: DVC берёт их из S3 по адресу изнутри кластера (remote cluster)
        cmds=["sh", "-c", PULL + "uv run --no-sync python -m churn.train"],
        env_vars={
            "MLFLOW_TRACKING_URI": "http://mlflow.mlops:5000",
            "TOTAL_ITERATIONS": "{{ params.TOTAL_ITERATIONS }}",
            "LEARNING_RATE": "{{ params.LEARNING_RATE }}",
            "DEPTH": "{{ params.DEPTH }}",
            "EVAL_METRIC": "{{ params.EVAL_METRIC }}",
            "EARLY_STOPPING_ROUNDS": "{{ params.EARLY_STOPPING_ROUNDS }}",
        },
        env_from=[k8s.V1EnvFromSource(secret_ref=k8s.V1SecretEnvSource(name="s3-credentials"))],
        do_xcom_push=True,
        get_logs=True,
        on_finish_action="delete_pod",
    )

    @task.short_circuit
    def promoted(result: dict) -> bool:
        print(
            f"версия {result['version']},"
            f" roc_auc {result['roc_auc']},"
            f" бывший champion {result['champion_before']}"
        )
        return result["promoted"]

    @task
    def rollout():
        from kubernetes import client, config

        config.load_incluster_config()
        now = datetime.now(UTC).isoformat()
        client.AppsV1Api().patch_namespaced_deployment(
            "churn-service", "default",
            {"spec": {"template": {"metadata": 
                                   {"annotations": {"kubectl.kubernetes.io/restartedAt": now}
                                   }}}},
        )
        print("churn-service перезапущен", now)

    validate >> train
    promoted(train.output) >> rollout()


churn_retrain()