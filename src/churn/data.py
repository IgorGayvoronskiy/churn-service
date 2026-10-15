"""Данные модели оттока: сырая выгрузка, очищенный слой и его схемы pandera.

  uv run python -m churn.data      шаг validate: чистка, проверка, отчёт в MLflow; при нарушениях код выхода 1

Сырой файл data/netflix_customer_churn.csv лежит в DVC и руками не правится. Чистка минимальная:
полные дубликаты строк убираются, строки с avg_watch_time_per_day больше 24 (часов в сутки)
удаляются, строковые поля обрезаются по пробелам. Дубли customer_id с разными
данными не убираем, их должна поймать схема. Схема проверяет уже очищенный слой: что пришло, то и проверяем.
"""
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

import pandas as pd
import pandera.pandas as pa

RAW_PATH = Path(os.getenv("DATA_PATH", "data/netflix_customer_churn.csv"))
EXPERIMENT = os.getenv("MLFLOW_EXPERIMENT", "churn")

CATEGORICAL = ["gender", "subscription_type", "region", "device", "payment_method", "favorite_genre"]
MISSING = "missing"

# правила для каждой строки: их можно проверить и на маленьком образце в CI
ROWS = pa.DataFrameSchema(
    {
        "customer_id": pa.Column(str, unique=True),
        # возраст: 18 - минимум в данных, верхней границы нет
        "age": pa.Column(int, pa.Check.ge(18)),
        "gender": pa.Column(str, pa.Check.isin(["Male", "Female", "Other", MISSING])),
        "subscription_type": pa.Column(str, pa.Check.isin(["Basic", "Standard", "Premium", MISSING])),
        "watch_hours": pa.Column(float, pa.Check.ge(0)),
        "last_login_days": pa.Column(int, pa.Check.ge(0)),
        "region": pa.Column(
            str,
            pa.Check.isin(["Africa", "Europe", "Asia", "Oceania", "South America", "North America", MISSING]),
        ),
        "device": pa.Column(str, pa.Check.isin(["TV", "Mobile", "Laptop", "Desktop", "Tablet", MISSING])),
        # месячная плата: в данных только три тарифа
        "monthly_fee": pa.Column(float, pa.Check.isin([8.99, 13.99, 17.99])),
        "churned": pa.Column(int, pa.Check.isin([0, 1])),
        "payment_method": pa.Column(
            str,
            pa.Check.isin(["Gift Card", "Crypto", "Debit Card", "PayPal", "Credit Card", MISSING]),
        ),
        # профилей в аккаунте: в данных 1..5
        "number_of_profiles": pa.Column(int, pa.Check.in_range(1, 5)),
        # часов в день: не больше 24 (строки выше 24 убирает clean)
        "avg_watch_time_per_day": pa.Column(float, pa.Check.in_range(0, 24)),
        "favorite_genre": pa.Column(
            str,
            pa.Check.isin(["Action", "Sci-Fi", "Drama", "Horror", "Romance", "Comedy", "Documentary", "Other", MISSING]),
        ),
    },
    strict=True,
)

# правила для выгрузки целиком: объём и распределение, на образце не проверить
EXPORT = pa.DataFrameSchema(
    ROWS.columns,
    checks=[
        pa.Check(lambda df: len(df) >= 2_500, error="меньше 2500 строк: выгрузка неполная"),
        pa.Check(lambda df: 0.4 <= df["churned"].mean() <= 0.6, error="доля оттока вне 0.4..0.6: сломан таргет или выборка?"),
        pa.Check(lambda df: 20 <= df["last_login_days"].median() <= 40, error="медиана last_login_days вне 20..40 дней"),
    ],
    strict=True,
)


def file_md5(path: Path) -> str:
    """Тот же md5, что DVC пишет в .dvc-файл: по нему видно, на какой версии данных обучена модель."""
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_raw(path: Path = RAW_PATH) -> pd.DataFrame:
    return pd.read_csv(path)


def clean(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw.drop_duplicates()
    # больше 24 часов в сутки невозможно;
    df = df[~(df["avg_watch_time_per_day"] > 24)].copy()
    df["customer_id"] = df["customer_id"].astype(str).str.strip()
    for c in CATEGORICAL:
        # как в train.py: пропуск превращается в "missing", это допустимое значение
        df[c] = df[c].fillna(MISSING).astype(str).str.strip()
    return df.reset_index(drop=True)


def load_clean(path: Path = RAW_PATH) -> pd.DataFrame:
    return EXPORT.validate(clean(load_raw(path)), lazy=True)


def main() -> int:
    import mlflow

    raw = load_raw()
    df = clean(raw)
    md5 = file_md5(RAW_PATH)
    mlflow.set_experiment(EXPERIMENT)
    with mlflow.start_run(run_name="validate"):
        mlflow.log_params({"step": "validate", "data": str(RAW_PATH), "data_md5": md5})
        mlflow.log_metrics({"raw_rows": len(raw), "clean_rows": len(df)})
        try:
            EXPORT.validate(df, lazy=True)
        except pa.errors.SchemaErrors as e:
            fc = e.failure_cases
            summary = fc.groupby(["column", "check"], dropna=False).size().rename("cases").reset_index()
            with tempfile.TemporaryDirectory() as tmp:
                fc.head(1000).to_csv(Path(tmp) / "failure_cases.csv", index=False)
                mlflow.log_artifact(str(Path(tmp) / "failure_cases.csv"))
            mlflow.log_metric("failed_checks", len(summary))
            mlflow.set_tag("valid", "false")
            print("данные не прошли проверку, отчёт failure_cases.csv в MLflow:")
            print(summary.to_string(index=False))
            return 1
        mlflow.set_tag("valid", "true")
        mlflow.log_metrics({"churn_rate": float(df["churned"].mean()), "customers": df["customer_id"].nunique()})
    result = {"valid": True, "data_md5": md5, "clean_rows": len(df),
              "churn_rate": round(float(df["churned"].mean()), 4),
              "customers": int(df["customer_id"].nunique())}
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())