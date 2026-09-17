import statistics
import requests

URL = "http://localhost:8000"

N = 10

def measure(endpoint: str, filename: str):
    with open(filename, "r", encoding="utf-8") as f:
        payload = __import__("json").load(f)

    latencies = []

    for i in range(N):
        response = requests.post(
            f"{URL}{endpoint}",
            json=payload,
        )

        response.raise_for_status()
        data = response.json()

        if endpoint == "/v1/predict":
            latency = data["latency_ms"]
        else:
            latency = data[0]["latency_ms"]

        latencies.append(latency)

        print(f"{i + 1:2d}: {latency:.2f} ms")

    median = statistics.median(latencies)

    return median, latencies


print("=== 1 строка ===")
median_single, single_values = measure(
    "/v1/predict",
    "good.json",
)

print("\n=== 500 строк ===")
median_batch, batch_values = measure(
    "/v1/predict/batch",
    "batch_good.json",
)

print("\n=== Результат ===")
print(f"1 строка:   {median_single:.2f} ms")
print(f"500 строк:  {median_batch:.2f} ms")
print(f"Отношение:  {median_batch / median_single:.2f}")