# Команды:
- uv sync
- uv run pytest
- docker compose up -d --build
- kind create cluster --name mlpro

# Скриншоты:
- pytest
  <img width="1351" height="563" alt="image_2026-09-15_19-22-47" src="https://github.com/user-attachments/assets/d44426c0-251b-4adb-aef1-9ff232a5b1e3" />
- SELECT запрос из логов
  <img width="1256" height="176" alt="image_2026-09-15_20-36-59" src="https://github.com/user-attachments/assets/744f0fdf-597d-4b0a-9f17-651263151e83" />
- kubectl get pods
  <img width="751" height="111" alt="image_2026-09-15_21-31-52" src="https://github.com/user-attachments/assets/6ca701ac-938e-4b68-8c3b-76673390e186" />
- predict через port-forward
  <img width="1091" height="105" alt="image_2026-09-15_21-34-09" src="https://github.com/user-attachments/assets/672c66ab-63d2-4624-b02f-88025ccd7531" />
  <img width="1260" height="103" alt="image_2026-09-15_21-33-48" src="https://github.com/user-attachments/assets/bad03a5a-3dcc-4851-9993-4927b57de9ae" />
- k9s
  <img width="1230" height="763" alt="image_2026-09-15_21-38-50" src="https://github.com/user-attachments/assets/6a221f03-3eb5-4458-a260-73bb9b7f7183" />

# Звёздочка 1
| Прогон | Метод | Endpoint | RPS | Median, ms | p95, ms | Max, ms | Доля ошибок |
|---:|:---:|:---|---:|---:|---:|---:|---:|
| 10 | GET | `/health` | 0.79 | 4 | 9 | 19.19 | 0.00% |
| 10 | POST | `/v1/predict` | 4.22 | 7 | 15 | 108.30 | 0.00% |
| 50 | GET | `/health` | 4.39 | 5 | 31 | 64.28 | 0.00% |
| 50 | POST | `/v1/predict` | 19.85 | 9 | 27 | 86.27 | 0.00% |
| 100 | GET | `/health` | 7.72 | 5 | 14 | 125.48 | 0.00% |
| 100 | POST | `/v1/predict` | 41.22 | 9 | 30 | 202.71 | 0.00% |

