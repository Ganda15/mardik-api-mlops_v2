"""FastAPI application exposing the model behind a stable HTTP contract."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from .model import get_model  # noqa: F401 — dependency target, wired by the route


def create_app() -> FastAPI:
    app = FastAPI(title="Mardik Model API", version="0.1.0")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/predict")
    def predict() -> JSONResponse:
        return JSONResponse(
            status_code=501,
            content={"detail": "predict endpoint not implemented yet"},
        )

    return app


app = create_app()
