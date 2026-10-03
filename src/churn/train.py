"""Обучение модели оттока: проверка данных, обучение, запись в MLflow, регистрация и гейт.

  MLFLOW_TRACKING_URI=http://127.0.0.1:5000 uv run python -m churn.train

Новая версия всегда получает алиас challenger. Алиас champion она получает, только если
ROC-AUC на отложенной выборке лучше, чем у текущего champion (или champion ещё нет).
"""
import hashlib
import json
import os
from pathlib import Path

import catboost
import matplotlib.pyplot as plt
import mlflow
import pandas as pd
import sklearn
from catboost import CatBoostClassifier, Pool
from mlflow import MlflowClient
from mlflow.exceptions import MlflowException
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split

DATA_PATH = Path(os.getenv("DATA_PATH", "data/netflix_customer_churn.csv"))
MODEL_NAME = os.getenv("MODEL_NAME", "churn")
EXPERIMENT = os.getenv("MLFLOW_EXPERIMENT", "churn")

TOTAL_ITERATIONS = int(os.getenv("TOTAL_ITERATIONS", "1000"))
LEARNING_RATE = float(os.getenv("LEARNING_RATE", "0.03"))
DEPTH = int(os.getenv("DEPTH", "6"))
EVAL_METRIC = os.getenv("EVAL_METRIC", "AUC")
EARLY_STOPPING_ROUNDS = int(os.getenv("EARLY_STOPPING_ROUNDS", "100"))

TOP_N_FEATURES = 10
MIN_GAIN = float(os.getenv("GATE_MIN_GAIN", "0.0002"))
SEED = 42

NUMERIC = [
    "age",
    "watch_hours",
    "last_login_days",
    "monthly_fee",
    "number_of_profiles",
    "avg_watch_time_per_day"
    ]
CATEGORICAL = [
    "gender",
    "subscription_type",
    "region",
    "device",
    "payment_method",
    "favorite_genre"
    ]
TARGET = "churned"

def load_data(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    return df


def prepare_features(df: pd.DataFrame):
    df = df.copy()

    if "customer_id" in df.columns:
        df = df.drop(columns=["customer_id"])

    missing = set(NUMERIC + CATEGORICAL + [TARGET]) - set(df.columns)
    if missing:
        raise ValueError(f"В данных нет колонок: {sorted(missing)}")
    if len(df) < 1000:
        raise ValueError(f"Слишком мало строк: {len(df)}")
    if not set(df[TARGET].unique()) <= {1, 0}:
        raise ValueError(f"Неожиданные значения таргета: {df[TARGET].unique()[:5]}")

    for c in CATEGORICAL:
        df[c] = df[c].fillna("missing").astype(str)

    X = df.drop(columns=[TARGET])
    y = df[TARGET].astype(int)

    return X, y

def split_data(X: pd.DataFrame, y: pd.Series):
    X_train_full, X_test, y_train_full, y_test = train_test_split(
        X, y, test_size=0.2, stratify=y, random_state=SEED
    )
    X_train, X_val, y_train, y_val = train_test_split(
        X_train_full,
        y_train_full,
        test_size=0.2,
        stratify=y_train_full,
        random_state=SEED,
    )
    return X_train, X_val, X_test, y_train, y_val, y_test

def train_catboost(X_train, y_train, X_val, y_val, cat_features):
    train_pool = Pool(X_train, y_train, cat_features=cat_features)
    val_pool = Pool(X_val, y_val, cat_features=cat_features)

    model = CatBoostClassifier(
        iterations=TOTAL_ITERATIONS,
        learning_rate=LEARNING_RATE,
        depth=DEPTH,
        loss_function="Logloss",
        eval_metric=EVAL_METRIC,
        random_seed=SEED,
        early_stopping_rounds=EARLY_STOPPING_ROUNDS,
        auto_class_weights="Balanced",
        verbose=100,
    )

    model.fit(train_pool, eval_set=val_pool, use_best_model=True)
    return model

def evaluate(model, X_test, y_test, threshold=0.5):
    proba = model.predict_proba(X_test)[:, 1]
    preds = (proba >= threshold).astype(int)

    metrics = {
        "ROC-AUC": roc_auc_score(y_test, proba),
        "Accuracy": accuracy_score(y_test, preds),
        "Precision": precision_score(y_test, preds),
        "Recall": recall_score(y_test, preds),
        "F1": f1_score(y_test, preds),
    }

    return metrics


def show_feature_importance(model, X_train, cat_features):
    pool = Pool(X_train, cat_features=cat_features)
    importances = model.get_feature_importance(pool)
    feat_imp = pd.Series(importances, index=X_train.columns).sort_values(ascending=False)

    return feat_imp

def plot_feature_importance(feat_imp: pd.Series, top_n: int = TOP_N_FEATURES):
    top = feat_imp.head(top_n).iloc[::-1]
    fig, ax = plt.subplots(figsize=(8, 0.4 * len(top) + 1.5))
    ax.barh(top.index, top.values)
    ax.set_xlabel("Важность (PredictionValuesChange)")
    ax.set_title("Важность признаков CatBoost")
    fig.tight_layout()
    return fig


def champion_auc(client: MlflowClient) -> tuple[str | None, float | None]:
    try:
        mv = client.get_model_version_by_alias(MODEL_NAME, "champion")
    except MlflowException:
        return None, None
    return mv.version, client.get_run(mv.run_id).data.metrics.get("ROC-AUC")


def file_md5(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> dict:
    data_md5 = file_md5(DATA_PATH)
    X, y = prepare_features(load_data(DATA_PATH))
    features = NUMERIC + CATEGORICAL
    X_train, X_val, X_test, y_train, y_val, y_test = split_data(X, y)

    model = train_catboost(X_train, y_train, X_val, y_val, cat_features=CATEGORICAL)
    metrics = evaluate(model, X_test, y_test)
    proba = model.predict_proba(X_val)[:, 1]
    _, recall, thresholds = precision_recall_curve(y_val, proba)
    threshold = float(thresholds[recall[:-1] >= 0.70].max())

    mlflow.set_experiment(EXPERIMENT)
    client = MlflowClient()
    with mlflow.start_run() as run:
        metadata = {
            "n_train": int(len(X_train)),
            "data_rows": int(len(X)),
            "features": list(X.columns),
            "numeric_cols": NUMERIC,
            "categorical_cols": CATEGORICAL,
            "threshold": float(round(threshold, 4)),
            "libs": {"sklearn": sklearn.__version__, "catboost": catboost.__version__},
        }
        mlflow.log_params({
            "TOTAL_ITERATIONS": TOTAL_ITERATIONS,
            "LEARNING_RATE": LEARNING_RATE,
            "DEPTH": DEPTH,
            "EVAL_METRIC": EVAL_METRIC,
            "EARLY_STOPPING_ROUNDS": EARLY_STOPPING_ROUNDS,
            "model": "CatBoostClassifier",
            "seed": SEED,
            "data": str(DATA_PATH),
            "data_md5": data_md5,
        })
        mlflow.log_metrics({**metrics, "threshold": threshold})
        mlflow.log_dict(metadata, "metadata.json")

        feat_imp = show_feature_importance(model, X_train, cat_features=CATEGORICAL)
        fig = plot_feature_importance(feat_imp)
        mlflow.log_figure(fig, "feature_importance.png")
        plt.close(fig)
        mlflow.log_dict(
            {k: float(v) for k, v in feat_imp.items()}, "feature_importance.json"
        )

        info = mlflow.catboost.log_model(model, name="model", registered_model_name=MODEL_NAME)
        version = info.registered_model_version

    old_version, old_auc = champion_auc(client)
    new_auc = float(metrics.get("ROC-AUC"))
    promoted = bool(old_auc is None or new_auc > old_auc + MIN_GAIN)
    client.set_registered_model_alias(MODEL_NAME, "challenger", version)
    if promoted:
        client.set_registered_model_alias(MODEL_NAME, "champion", version)

    result = {"run_id": run.info.run_id, "version": version,
              "roc_auc": round(metrics.get("ROC-AUC"), 4),
              "champion_before": old_version, "champion_auc_before": old_auc,
              "promoted": promoted}
    print(json.dumps(result, ensure_ascii=False))
    xcom = Path("/airflow/xcom")
    if xcom.is_dir():
        (xcom / "return.json").write_text(json.dumps(result))
    return result


if __name__ == "__main__":
    main()