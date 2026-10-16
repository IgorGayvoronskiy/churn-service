import pandas as pd
import pandera.pandas as pa
import pytest

from churn.data import EXPORT, ROWS, clean


@pytest.fixture()
def raw():
    """Небольшой пример сырой выгрузки из трёх клиентов."""
    return pd.DataFrame({
        "customer_id": ["1001", "1002", "1003"],
        "age": [25, 35, 45],
        "gender": ["Male", "Female", "Other"],
        "subscription_type": ["Basic", "Standard", "Premium"],
        "watch_hours": [10.0, 20.0, 30.0],
        "last_login_days": [20, 30, 40],
        "region": ["Europe", "Asia", "Africa"],
        "device": ["TV", "Mobile", "Laptop"],
        "monthly_fee": [8.99, 13.99, 17.99],
        "churned": [0, 1, 0],
        "payment_method": ["PayPal", "Credit Card", "Debit Card"],
        "number_of_profiles": [1, 3, 5],
        "avg_watch_time_per_day": [2.0, 4.0, 6.0],
        "favorite_genre": ["Drama", "Comedy", "Action"],
    })


def test_valid_rows_pass(raw):
    """Корректные данные проходят очистку и проверку построчной схемой."""
    df = clean(raw)

    validated = ROWS.validate(df, lazy=True)

    assert len(validated) == 3
    assert validated["customer_id"].is_unique


def test_invalid_age_is_caught(raw):
    """Возраст меньше 18 лет нарушает схему."""
    bad = clean(raw)
    bad.loc[0, "age"] = 17

    with pytest.raises(pa.errors.SchemaErrors) as exc:
        ROWS.validate(bad, lazy=True)

    failure_cases = exc.value.failure_cases
    assert "age" in set(failure_cases["column"])


def test_small_export_is_rejected(raw):
    """Выгрузка из трёх строк не проходит проверку полного датасета."""
    df = clean(raw)

    with pytest.raises(pa.errors.SchemaErrors) as exc:
        EXPORT.validate(df, lazy=True)

    checks = set(exc.value.failure_cases["check"].dropna().astype(str))
    assert any(
        "меньше 2500 строк" in check
        for check in checks
    )


def test_clean(raw):
    """
    Очистка удаляет полные дубликаты и строки со значением avg_watch_time_per_day более 24 часов.
    """
    duplicate = raw.iloc[[0]].copy()
    impossible = raw.iloc[[1]].copy()
    impossible.loc[:, "customer_id"] = "1004"
    impossible.loc[:, "avg_watch_time_per_day"] = 25.0

    dirty = pd.concat(
        [raw, duplicate, impossible],
        ignore_index=True,
    )

    df = clean(dirty)

    assert len(df) == 3
    assert df["customer_id"].tolist() == ["1001", "1002", "1003"]
