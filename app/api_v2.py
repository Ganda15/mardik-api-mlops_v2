"""Contrat ``/v2`` — la nouvelle version. [STUB]

Contrat attendu (c'est celui que testent ``tests/acceptance/test_chaine.py``
et que consomme la gateway) :

    POST /v2/analyse   {"texte": "<contrat>", "contrat_id": "c07" (optionnel)}
    → 200 {
        "clauses": [{"type": "résiliation", "extrait": "...", "confiance": 0.91,
                     "sections": [3]}, ...],
        "confiance_globale": 0.87,
        "modele": "...", "version": "v2.0.0",
        "sections": 14,            # nombre de sections analysées
        "appels_llm": 14,
        "latence_ms": 5230.4,
        "cout_eur": 0.031
      }
    → 422 corps invalide (détail explicite)
    → 503 fournisseur LLM indisponible (détail explicite)
    Jamais de 500 brut : toute erreur est explicite et journalisée.

Règles :
* aucune troncature : le contrat passe par ``pipeline.decouper`` puis chaque
  section par ``pipeline.extraire`` (map), ``pipeline.consolider`` (reduce),
  et ``pipeline.scorer`` calcule les confiances ;
* la fonction ``analyser_v2(texte, client, telemetry)`` doit exister et être
  réutilisable hors HTTP (le gate d'évaluation l'appelle directement) ;
* chaque requête produit une ``Mesure`` (version, latence, score, coût,
  appels LLM, erreur) dans ``telemetry.metriques`` et des spans
  ``analyse.requete`` → ``llm.appel`` (un par section), comme la v1.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.llm_client import Bundle, LLMClient
from app.telemetry import Telemetry, build_default_telemetry

router = APIRouter(prefix="/v2", tags=["v2"])
VERSION_V2 = "v2"


class RequeteAnalyseV2(BaseModel):
    texte: str = Field(..., min_length=20, description="Texte intégral du contrat")
    contrat_id: str | None = None


class ClauseV2(BaseModel):
    type: str
    extrait: str
    confiance: float
    sections: list[int]


class ReponseAnalyseV2(BaseModel):
    clauses: list[ClauseV2]
    confiance_globale: float
    modele: str
    version: str
    sections: int
    appels_llm: int
    latence_ms: float
    cout_eur: float


def get_bundle_v2() -> Bundle:
    return Bundle.charger(VERSION_V2)


def get_client_v2(bundle: Bundle = Depends(get_bundle_v2)) -> LLMClient:
    return LLMClient(bundle)


def get_telemetry() -> Telemetry:
    return build_default_telemetry()


def analyser_v2(texte: str, client: LLMClient, telemetry: Telemetry) -> ReponseAnalyseV2:
    raise NotImplementedError("api_v2.analyser_v2 — le contrat v2 (map-reduce par clauses)")


@router.post("/analyse", response_model=ReponseAnalyseV2)
def analyse(
    requete: RequeteAnalyseV2,
    client: LLMClient = Depends(get_client_v2),
    telemetry: Telemetry = Depends(get_telemetry),
) -> ReponseAnalyseV2:
    # À faire : appeler analyser_v2 et traduire ErreurLLM en 503 explicite (voir api_v1).
    raise NotImplementedError("api_v2.analyse — la route POST /v2/analyse")
