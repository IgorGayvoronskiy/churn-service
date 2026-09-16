import pytest

def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert "model_version" in r.json()


def test_ready(client):
    assert client.get("/ready").status_code == 200


def test_bad_tenure_is_422(client, good_row):
    r = client.post("/v1/predict", json={**good_row, "watch_hours": -1})
    assert r.status_code == 422


def test_missing_field_is_422(client, good_row):
    row = dict(good_row)
    del row["age"]
    assert client.post("/v1/predict", json=row).status_code == 422


def test_extra_field_is_422(client, good_row):
    r = client.post("/v1/predict", json={**good_row, "hacker_field": 1})
    assert r.status_code == 422

def test_age_zero_is_422(client, good_row):
    r = client.post("/v1/predict", json={**good_row, "age": 0})
    assert r.status_code == 422

def test_zero_profiles_is_422(client, good_row):
    r = client.post(
        "/v1/predict",
        json={**good_row, "number_of_profiles": 0}
    )
    assert r.status_code == 422

def test_zero_watch_hours_is_valid(client, good_row):
    r = client.post(
        "/v1/predict",
        json={**good_row, "watch_hours": 0}
    )
    assert r.status_code == 200

def test_zero_last_login_days_is_valid(client, good_row):
    r = client.post(
        "/v1/predict",
        json={**good_row, "last_login_days": 0}
    )
    assert r.status_code == 200

def test_zero_avg_watch_time_is_valid(client, good_row):
    r = client.post(
        "/v1/predict",
        json={**good_row, "avg_watch_time_per_day": 0}
    )
    assert r.status_code == 200

@pytest.mark.parametrize(
    "field",
    [
        "age",
        "gender",
        "subscription_type",
        "watch_hours",
        "last_login_days",
        "region",
        "device",
        "monthly_fee",
        "payment_method",
        "number_of_profiles",
        "avg_watch_time_per_day",
        "favorite_genre",
    ],
)
def test_missing_required_field_is_422(client, good_row, field):
    row = dict(good_row)
    del row[field]

    r = client.post("/v1/predict", json=row)

    assert r.status_code == 422