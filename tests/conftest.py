import pytest
from fastapi.testclient import TestClient

from churn.service.app import app


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def good_row():
    return {
        "age": 24,
        "gender": "Female",
        "subscription_type": "Standard",
        "watch_hours": 5.56,
        "last_login_days": 32,
        "region": "Europe",
        "device": "Laptop",
        "monthly_fee": 13.99,
        "payment_method": "PayPal",
        "number_of_profiles": 1,
        "avg_watch_time_per_day": 0.17,
        "favorite_genre": "Drama",
    }
