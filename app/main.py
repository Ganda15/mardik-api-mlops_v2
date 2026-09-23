"""Application FastAPI — [FOURNI].

* ``/v1`` est branché et fonctionnel (le contrat historique) ;
* ``/v2`` et ``/analyse`` (gateway) sont branchés sur des stubs : tant qu'un
  module lève ``NotImplementedError``, la route répond **501** avec le nom du
  chantier restant — jamais un 500 muet.
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse

from app import api_v1, api_v2, gateway
from app.securite import garde_instance_publique, verifier_configuration
from app.telemetry import build_default_telemetry

# Brique F2 : la page unique du juriste (conception Ch1, H15), servie par l'API elle-même.
PAGE_ACCUEIL = Path(__file__).resolve().parent / "static" / "index.html"


def create_app() -> FastAPI:
    verifier_configuration()  # brique F3 : une instance publique sans clé ne démarre pas
    app = FastAPI(title="Mardik — analyse de contrats", version="2.0.0")
    build_default_telemetry()
    # Brique F3 : sans effet tant que MARDIK_API_KEY / MARDIK_BUDGET_JOUR_EUR ne sont pas posées.
    app.middleware("http")(garde_instance_publique)

    app.include_router(api_v1.router)
    app.include_router(api_v2.router)
    app.include_router(gateway.router)

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def page_accueil() -> HTMLResponse:
        return HTMLResponse(PAGE_ACCUEIL.read_text(encoding="utf-8"))

    @app.get("/health")
    def health() -> dict[str, str]:
        return {
            "status": "ok",
            "provider": os.environ.get("LLM_PROVIDER", "ollama"),
            "mock": os.environ.get("MOCK", "off"),
        }

    @app.exception_handler(NotImplementedError)
    async def _non_implemente(request: Request, exc: NotImplementedError) -> JSONResponse:
        return JSONResponse(
            status_code=501,
            content={"detail": f"à implémenter : {exc or 'module non implémenté'}"},
        )

    return app


app = create_app()
