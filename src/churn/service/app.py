import time
import uuid
from contextlib import asynccontextmanager

import joblib
import pandas as pd
from fastapi import BackgroundTasks, FastAPI, HTTPException
from pydantic import BaseModel, Field

from churn import db
from churn.config import settings


class Features(BaseModel):
    model_config = {"extra": "forbid"}

    age: int = Field(gt=0)
    gender: str
    subscription_type: str
    watch_hours: float = Field(ge=0)
    last_login_days: int = Field(ge=0)
    region: str
    device: str
    monthly_fee: float
    payment_method: str
    number_of_profiles:	int = Field(gt=0)
    avg_watch_time_per_day: float = Field(ge=0)
    favorite_genre: str

class BatchFeatures(BaseModel):
    model_config = {"extra": "forbid"}

    rows: list[Features] = Field(min_length=1, max_length=1000)

class Prediction(BaseModel):
    request_id: str
    score: float
    churn: bool
    model_version: str
    latency_ms: float

@asynccontextmanager
async def lifespan(app: FastAPI):
    bundle = joblib.load(settings.model_path)

    app.state.model = bundle['model']
    app.state.meta = bundle['metadata']
    app.state.version = bundle['metadata']['model_version']

    db.init()
    yield
    app.state.model = None

app = FastAPI(title="churn-service", version="1.0", lifespan=lifespan)

@app.get("/health")
def health():
    return {"status": "ok", "model_version": getattr(app.state, "version", "unknown")}

@app.get("/ready")
def ready():
    if getattr(app.state, "pipeline", "None") is  None:
        raise HTTPException(status_code=503, detail="Model not loaded")
    
    return {"status": "ready"}

@app.post("/v1/predict")
def predict(x: Features, bg: BackgroundTasks) -> Prediction:
    t0 = time.perf_counter()
    request_id = str(uuid.uuid4())
    payload = x.model_dump()
    frame = pd.DataFrame([payload]).reindex(columns=app.state.meta["features"])

    score = float(app.state.model.predict_proba(frame)[0, 1])

    latency_ms = round((time.perf_counter() - t0) * 1000, 2)

    bg.add_task(db.save_prediction, request_id, payload, score, app.state.version, latency_ms, 200)

    churn = score >= app.state.meta["threshold"]

    return Prediction(score=score, churn=churn, model_version=app.state.version, request_id=request_id, latency_ms=latency_ms)

@app.post("/v1/predict/batch")
def predict_batch(x: BatchFeatures, bg: BackgroundTasks) -> list[Prediction]:
    t0 = time.perf_counter()

    payloads = [row.model_dump() for row in x.rows]

    frame = pd.DataFrame(payloads).reindex(columns=app.state.meta["features"])

    scores = app.state.model.predict_proba(frame)[:, 1]

    latency_ms = round((time.perf_counter() - t0) * 1000, 2)

    results = []
    for payload, score in zip(payloads, scores):
        request_id = str(uuid.uuid4())
        score = float(score)
        
        bg.add_task(db.save_prediction, request_id, payload, score, app.state.version, latency_ms, 200)

        churn = score >= app.state.meta["threshold"]
        
        results.append(Prediction(score=score, churn=churn, model_version=app.state.version, request_id=request_id, latency_ms=latency_ms))

    return results
