"""Contrat ``/v2`` — la nouvelle version. Brique 6.

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
* aucune troncature : le contrat passe par ``pipeline.decouper`` puis chaque section par
  ``pipeline.extraire`` (map), ``pipeline.consolider`` (reduce), et ``pipeline.scorer``
  calcule les confiances ;
* ``analyser_v2(texte, client, telemetry)`` existe séparément de la route, réutilisable
  hors HTTP (le gate d'évaluation, brique 7, l'appellera directement) ;
* une panne réseau sur UNE section (``ErreurLLM`` levée par ``client.completer()``) arrête
  toute l'analyse — ce n'est pas la même chose qu'une clause individuelle mal formée dans
  une réponse par ailleurs valide (celle-là, ``extraire()`` l'ignore déjà, brique 3) ;
* chaque requête produit une ``Mesure`` (version, latence, score, coût, appels LLM, erreur)
  et des spans ``analyse.requete`` → ``llm.appel`` (un par section), comme la v1.
"""
from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.llm_client import Bundle, ErreurLLM, LLMClient
from app.pipeline.confiance import Clause, scorer
from app.pipeline.consolidation import consolider
from app.pipeline.decoupage import decouper
from app.pipeline.extraction import extraire
from app.telemetry import Mesure, Telemetry, build_default_telemetry

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
    bundle = client.bundle
    taille_max = int(bundle.parametres.get("contexte_max_caracteres", 6000))
    debut = time.perf_counter()

    with telemetry.tracer.start_as_current_span("analyse.requete") as span:
        span.set_attribute("mardik.version", bundle.version)
        sections = decouper(texte, taille_max=taille_max)
        span.set_attribute("mardik.sections", len(sections))

        par_section: list[list[Clause]] = []
        cout_total = 0.0
        try:
            for section in sections:
                with telemetry.tracer.start_as_current_span("llm.appel") as span_llm:
                    clauses, reponse_llm = extraire(section, client)
                    span_llm.set_attribute("llm.latence_ms", reponse_llm.latence_ms)
                    span_llm.set_attribute("llm.tokens", reponse_llm.tokens)
                cout_total += client.cout_eur(reponse_llm)
                par_section.append(clauses)
        except ErreurLLM as exc:
            latence = (time.perf_counter() - debut) * 1000
            telemetry.metriques.enregistrer(
                Mesure(
                    ts=time.time(),
                    version=bundle.version,
                    route="/v2/analyse",
                    latence_ms=latence,
                    erreur=True,
                )
            )
            telemetry.logger.error("analyse.echec", version=bundle.version, cause=str(exc))
            raise

        clauses_consolidees = consolider(par_section)
        clauses_notees, confiance_globale = scorer(clauses_consolidees, texte)

        latence = (time.perf_counter() - debut) * 1000
        telemetry.metriques.enregistrer(
            Mesure(
                ts=time.time(),
                version=bundle.version,
                route="/v2/analyse",
                latence_ms=latence,
                erreur=False,
                score=confiance_globale,
                cout_eur=round(cout_total, 6),
                appels_llm=len(sections),
                tronque=False,
            )
        )
        telemetry.logger.info(
            "analyse.terminee",
            version=bundle.version,
            latence_ms=round(latence, 1),
            clauses=len(clauses_notees),
            sections=len(sections),
        )

    return ReponseAnalyseV2(
        clauses=[
            ClauseV2(type=c.type, extrait=c.extrait, confiance=c.confiance, sections=c.sections)
            for c in clauses_notees
        ],
        confiance_globale=confiance_globale,
        modele=bundle.modele,
        version=bundle.version,
        sections=len(sections),
        appels_llm=len(sections),
        latence_ms=latence,
        cout_eur=round(cout_total, 6),
    )


@router.post("/analyse", response_model=ReponseAnalyseV2)
def analyse(
    requete: RequeteAnalyseV2,
    client: LLMClient = Depends(get_client_v2),
    telemetry: Telemetry = Depends(get_telemetry),
) -> ReponseAnalyseV2:
    try:
        return analyser_v2(requete.texte, client, telemetry)
    except ErreurLLM as exc:
        raise HTTPException(status_code=503, detail=f"fournisseur LLM indisponible : {exc}")
