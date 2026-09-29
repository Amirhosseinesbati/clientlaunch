"""Internal planning API used by n8n. No business writes are performed here."""

import hashlib
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException

from .adapters import ConnectedScopeExtractor, DemoScopeExtractor
from .graph import build_graph
from .models import PlanRequest, PlanResponse


def check_internal_key(x_internal_key: str = Header(default="")) -> None:
    expected = os.environ.get("INTERNAL_KEY", "")
    if not expected or not x_internal_key or not __import__("hmac").compare_digest(x_internal_key, expected):
        raise HTTPException(status_code=401, detail="Internal authentication required")


@asynccontextmanager
async def lifespan(app: FastAPI):
    mode = os.environ.get("MODEL_MODE", "demo")
    extractor = DemoScopeExtractor() if mode == "demo" else ConnectedScopeExtractor() if mode == "connected" else None
    if extractor is None:
        raise RuntimeError("MODEL_MODE must be demo or connected")
    dsn = os.environ.get("AI_CHECKPOINT_DSN")
    if dsn:
        from langgraph.checkpoint.postgres import PostgresSaver

        with PostgresSaver.from_conn_string(dsn) as saver:
            saver.setup()
            app.state.graph = build_graph(extractor, checkpointer=saver)
            yield
    else:
        app.state.graph = build_graph(extractor)
        yield


app = FastAPI(title="ClientLaunch planning service", version="0.1.0", lifespan=lifespan)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "model_mode": os.environ.get("MODEL_MODE", "demo")}


@app.post("/plan", response_model=PlanResponse, dependencies=[Depends(check_internal_key)])
def plan(request: PlanRequest) -> PlanResponse:
    # Caller IDs are data, never checkpoint identifiers or authorization.
    fingerprint = hashlib.sha256(request.model_dump_json().encode("utf-8")).hexdigest()[:40]
    try:
        result = app.state.graph.invoke({"request": request}, {"configurable": {"thread_id": fingerprint}, "recursion_limit": 12})
        return result["response"]
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
