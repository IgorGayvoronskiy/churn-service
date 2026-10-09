import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import Literal

import pandas as pd
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from prometheus_client import Counter, Gauge, Histogram
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

from churn import db
from churn.config import settings
from churn.model_store import load_model

PREDICTIONS = Counter("churn_predictions_total", "Predictions by class", ["churn"])
SCORE = Histogram("churn_score", "Predicted churn probability", buckets=[i / 10 for i in range(11)])
MODEL_INFO = Gauge("churn_model_info", "Model loaded by this pod", ["version"])
LATENCY_BUCKETS = (0.003, 0.005, 0.0075, 0.01, 0.015, 0.02, 0.03, 0.05, 0.1, 0.25, 0.5, 1)

FEATURE_BUCKETS = {
    "age": tuple(range(0, 100, 5)),
    "watch_hours": (0.5, 1, 2, 5, 10, 15, 20, 30, 40, 50, 75, 110),
    "last_login_days": (0, 1, 2, 3, 5, 7, 10, 15, 20, 30, 45, 60, 90),
    "monthly_fee": (8.99, 13.99, 17.99),
    "number_of_profiles": (1, 2, 3, 4, 5),
    "avg_watch_time_per_day": (0.25, 0.5, 1, 1.5, 2, 3, 4, 5, 6, 8, 10, 12, 16, 24),
}
FEATURE_BUCKETS = {
    "age": (20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 80),
    "watch_hours": (0.5, 1, 2, 4, 6, 8, 10, 15, 20, 30, 40, 60, 80, 120),
    "last_login_days": (0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 90),
    "monthly_fee": (8.99, 13.99, 17.99),
    "number_of_profiles": (1, 2, 3, 4, 5, 10),
    "avg_watch_time_per_day": (0, 0.05, 0.1, 0.2, 0.3, 0.5, 0.75, 1, 2, 5, 10, 24, 100),
}
FEATURE_HISTS = {
    col: Histogram(f"churn_feature_{col}", f"Distribution of {col} in requests", buckets=b)
    for col, b in FEATURE_BUCKETS.items()
}


def _observe_features(payload: dict) -> None:
    for col, hist in FEATURE_HISTS.items():
        value = payload.get(col)
        if value is not None:
            hist.observe(value)


class Features(BaseModel):
    model_config = {"extra": "forbid"}

    age: int = Field(ge=18)
    gender: str
    subscription_type: str
    watch_hours: float = Field(ge=0)
    last_login_days: int = Field(ge=0)
    region: str
    device: str
    monthly_fee: Literal[8.99, 13.99, 17.99]
    payment_method: str
    number_of_profiles:	int = Field(ge=1)
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

    app.state.model, app.state.meta, app.state.version = load_model()
    MODEL_INFO.labels(app.state.version).set(1)

    db.init()
    yield
    app.state.model = None


app = FastAPI(title="churn-service", version="1.0", lifespan=lifespan)
Instrumentator().instrument(app, latency_lowr_buckets=LATENCY_BUCKETS).expose(app)

@app.get("/health")
def health():
    return {
        "status": "ok",
        "model_version": getattr(app.state, "version", "unknown"),
        "model_path": settings.model_path,
    }


@app.get("/ready")
def ready():
    if getattr(app.state, "model", "None") is None:
        raise HTTPException(status_code=503, detail="Model not loaded")
    
    return {"status": "ready"}


logger = logging.getLogger(__name__)

async def _safe_body(request: Request):
    try:
        return await request.json()
    except Exception:
        raw = await request.body()
        return {"raw": raw.decode("utf-8", errors="replace")}


PREDICT_PATHS = {"/v1/predict", "/v1/predict/batch"}

def _log_failure_task(
        request_id: str,
        body,
        status_code: int,
        request: Request
)-> BackgroundTask | None:
    if request.url.path not in PREDICT_PATHS:
        return None
    
    return BackgroundTask(
        db.save_prediction,
        request_id,
        body,
        None,
        getattr(app.state, "version", "unknown"),
        None,
        status_code,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    request_id = str(uuid.uuid4())
    body = await _safe_body(request)

    return JSONResponse(
        status_code=422,
        content={"request_id": request_id, "detail": jsonable_encoder(exc.errors())},
        background=_log_failure_task(request_id, body, 422, request),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s", request.url.path)
    request_id = str(uuid.uuid4())
    body = await _safe_body(request)

    return JSONResponse(
        status_code=500,
        content={"request_id": request_id, "detail": "Internal server error"},
        background=_log_failure_task(request_id, body, 500, request),
    )


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
    
    PREDICTIONS.labels(str(churn).lower()).inc()
    SCORE.observe(score)
    _observe_features(payload)

    return Prediction(
        score=score,
        churn=churn,
        model_version=app.state.version,
        request_id=request_id,
        latency_ms=latency_ms,
    )


@app.post("/v1/predict/batch")
def predict_batch(x: BatchFeatures, bg: BackgroundTasks) -> list[Prediction]:
    t0 = time.perf_counter()

    payloads = [row.model_dump() for row in x.rows]

    frame = pd.DataFrame(payloads).reindex(columns=app.state.meta["features"])

    scores = app.state.model.predict_proba(frame)[:, 1]

    latency_ms = round((time.perf_counter() - t0) * 1000, 2)

    results = []
    for payload, score in zip(payloads, scores, strict=True):
        score = float(score)
        request_id = str(uuid.uuid4())
        
        bg.add_task(
            db.save_prediction,
            request_id,
            payload,
            score,
            app.state.version,
            latency_ms,
            200,
        )

        churn = score >= app.state.meta["threshold"]
        PREDICTIONS.labels(str(churn).lower()).inc()
        SCORE.observe(score)
        _observe_features(payload)

        results.append(
            Prediction(
                score=score,
                churn=churn,
                model_version=app.state.version,
                request_id=request_id,
                latency_ms=latency_ms
            )
        )

    return results
