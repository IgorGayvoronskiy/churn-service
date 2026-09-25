from locust import HttpUser, between, task


class ChurnServiceUser(HttpUser):
    wait_time = between(1, 3)

    @task(5)
    def predict(self):
        payload = {
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

        self.client.post(
            "/v1/predict",
            json=payload,
            name="/v1/predict",
        )

    @task(1)
    def health(self):
        self.client.get(
            "/health",
            name="/health",
        )