"""Gateway : routeur canary entre les versions livrées. [STUB]

Contrat attendu :

    POST /analyse  {"texte": "..."}         → réponse de la version choisie,
                                              + en-tête ``X-Mardik-Version``
    GET  /gateway/etat                      → {"active": "v1.0.0", "canary": "v2.0.0",
                                               "canary_percent": 10}

    choisir_version(active, canary, canary_percent, tirage) -> str
        fonction pure : ``tirage`` ∈ [0, 100[ ; renvoie ``canary`` si un canary
        est déployé et ``tirage < canary_percent``, sinon ``active``.

Règles :
* la gateway lit ``ops/registry/index.json`` (via ``Registry``) à **chaque**
  requête : une promotion ou un rollback doit prendre effet sans redémarrage ;
* ``CANARY_PERCENT`` dans ``.env`` force le pourcentage (sinon celui de
  l'index) — pratique pour la démo ;
* le bundle de chaque version vient du registre (``registry.bundle(version)``),
  pas de ``models/`` : on sert ce qui a été livré, pas ce qui est en chantier ;
* la stratégie du bundle décide du moteur : ``monolithique`` → ``analyser_v1``,
  ``map_reduce_clauses`` → ``analyser_v2`` ;
* les erreurs restent explicites (422 / 503), comme sur ``/v1`` et ``/v2``.
"""
from __future__ import annotations

import os
import random

from fastapi import APIRouter, Depends, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.api_v1 import analyser_v1
from app.api_v2 import analyser_v2, nouveau_request_id
from app.llm_client import ErreurLLM, LLMClient
from app.telemetry import Telemetry, build_default_telemetry
from ops.registry import Registry

router = APIRouter(tags=["gateway"])


class RequeteAnalyse(BaseModel):
    texte: str = Field(..., min_length=20)
    contrat_id: str | None = None


def choisir_version(
    active: str, canary: str | None, canary_percent: int, tirage: float
) -> str:
    if canary is not None and tirage < canary_percent:
        return canary
    return active


def pourcentage_effectif(idx: dict) -> tuple[int, str]:
    """(pourcentage appliqué, source) — ``CANARY_PERCENT`` force la valeur du registre.

    Vide = absent : ``CANARY_PERCENT=`` dans un .env ne doit ni planter (``int('')``)
    ni forcer 0. Constaté le 22/09 : l'env forçait 10 % pendant que /gateway/etat
    annonçait 50 % — les deux routes passent désormais par ici.
    """
    force = os.environ.get("CANARY_PERCENT", "").strip()
    if force:
        return int(force), "env:CANARY_PERCENT"
    return int(idx.get("canary_percent", 0) or 0), "registre"


def get_registry() -> Registry:
    return Registry()


def get_telemetry() -> Telemetry:
    return build_default_telemetry()


@router.get("/gateway/etat")
def etat(registry: Registry = Depends(get_registry)) -> dict:
    idx = registry.index()
    pct, source = pourcentage_effectif(idx)
    return {
        "active": idx.get("active"),
        "canary": idx.get("canary"),
        "canary_percent": pct,
        "canary_percent_registre": int(idx.get("canary_percent", 0) or 0),
        "source": source,
    }


@router.post("/analyse", response_model=None)
def analyse(
    requete: RequeteAnalyse,
    response: Response,
    registry: Registry = Depends(get_registry),
    telemetry: Telemetry = Depends(get_telemetry),
) -> dict | JSONResponse:
    rid = nouveau_request_id()
    idx = registry.index()
    active = idx.get("active")
    canary = idx.get("canary")
    canary_percent, _ = pourcentage_effectif(idx)

    tirage = random.uniform(0, 100)
    version_servie = choisir_version(active, canary, canary_percent, tirage)

    bundle = registry.bundle(version_servie)
    client = LLMClient(bundle)

    try:
        if bundle.strategie == "map_reduce_clauses":
            reponse = analyser_v2(requete.texte, client, telemetry, request_id=rid)
        else:
            reponse = analyser_v1(requete.texte, client, telemetry)
    except ErreurLLM as exc:
        # Le frontend passe par ici : une panne reste explicite, signée et corrélable.
        return JSONResponse(
            status_code=503,
            content={"detail": f"fournisseur LLM indisponible : {exc}", "request_id": rid},
            headers={"X-Mardik-Version": version_servie},
        )

    response.headers["X-Mardik-Version"] = version_servie
    return reponse.model_dump()
