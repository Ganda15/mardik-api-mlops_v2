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
  et des spans ``analyse.requete`` → ``llm.appel`` (un par section), comme la v1 ;
* les sections sont indépendantes : elles sont analysées **en parallèle** (``parallelisme``
  du bundle, 4 par défaut), l'ordre des résultats est conservé (brique 12 — constat Jaeger
  du 21/09 : en série, 18 sections × 22,7 s = ~6 min par contrat, pour 8 s exigées).
"""
from __future__ import annotations

import contextvars
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Depends, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.llm_client import Bundle, ErreurLLM, LLMClient
from app.pipeline.confiance import Clause, clauses_prouvees, libeller, scorer
from app.pipeline.consolidation import consolider
from app.pipeline.decoupage import Section, decouper, regrouper
from app.pipeline.extraction import extraire
from app.telemetry import Mesure, Telemetry, build_default_telemetry

router = APIRouter(prefix="/v2", tags=["v2"])
VERSION_V2 = "v2"


TAILLE_MAX_TEXTE = 200_000  # ~65 pages : le plus gros contrat de référence (c12) est à ~31 sections

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
    libelle: str  # niveau de certitude pour le juriste : haute / moyenne / basse (H6)
    request_id: str  # corrélation réponse ↔ journaux ↔ trace (spec §2, champ additif)
    modele: str
    version: str
    sections: int
    appels_llm: int
    latence_ms: float
    cout_eur: float


def nouveau_request_id() -> str:
    """``req_`` + 12 caractères hexadécimaux : unique par requête, lisible au téléphone."""
    return f"req_{uuid.uuid4().hex[:12]}"


def get_bundle_v2() -> Bundle:
    return Bundle.charger(VERSION_V2)


def get_client_v2(bundle: Bundle = Depends(get_bundle_v2)) -> LLMClient:
    return LLMClient(bundle)


def get_telemetry() -> Telemetry:
    return build_default_telemetry()


def analyser_v2(
    texte: str, client: LLMClient, telemetry: Telemetry, request_id: str | None = None
) -> ReponseAnalyseV2:
    bundle = client.bundle
    rid = request_id or nouveau_request_id()
    taille_max = int(bundle.parametres.get("contexte_max_caracteres", 6000))
    debut = time.perf_counter()

    with telemetry.tracer.start_as_current_span("analyse.requete") as span:
        span.set_attribute("mardik.version", bundle.version)
        span.set_attribute("mardik.request_id", rid)
        sections = decouper(texte, taille_max=taille_max)
        # Brique 19 : des sections voisines regroupées = moins d'appels, donc une queue de latence
        # plus courte (on attend le plus lent). 0 dans le bundle = comportement d'origine.
        sections = regrouper(sections, int(bundle.parametres.get("regroupement_caracteres", 0)))
        span.set_attribute("mardik.sections", len(sections))

        parallelisme = max(1, int(bundle.parametres.get("parallelisme", 4)))

        def _traiter(section: Section) -> tuple[list[Clause], float, int, int]:
            with telemetry.tracer.start_as_current_span("llm.appel") as span_llm:
                span_llm.set_attribute("mardik.section", section.indice)
                clauses, reponse_llm = extraire(section, client)
                span_llm.set_attribute("llm.latence_ms", reponse_llm.latence_ms)
                span_llm.set_attribute("llm.tokens", reponse_llm.tokens)
            return clauses, client.cout_eur(reponse_llm), reponse_llm.tokens_entree, reponse_llm.tokens_sortie

        # Un contexte copié PAR tâche (un même Context ne peut pas être entré par deux
        # threads) : analyse.requete reste le parent de chaque llm.appel dans la trace.
        taches = [(contextvars.copy_context(), s) for s in sections]
        executor = ThreadPoolExecutor(max_workers=min(parallelisme, max(1, len(sections))))
        try:
            resultats = list(executor.map(lambda t: t[0].run(_traiter, t[1]), taches))
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
            telemetry.logger.error(
                "analyse.echec", version=bundle.version, request_id=rid, cause=str(exc)
            )
            raise
        finally:
            # cancel_futures : une panne sur la section 2 n'appelle (ne paie) pas les suivantes
            executor.shutdown(wait=True, cancel_futures=True)

        par_section = [r[0] for r in resultats]
        cout_total = sum(r[1] for r in resultats)
        tokens_entree = sum(r[2] for r in resultats)
        tokens_sortie = sum(r[3] for r in resultats)

        clauses_consolidees = consolider(par_section)
        clauses_notees, _ = scorer(clauses_consolidees, texte)
        # Une clause sans extrait vérifié n'est pas une détection (voir clauses_prouvees) :
        # le score global est recalculé sur les seules clauses prouvées.
        clauses_notees = clauses_prouvees(clauses_notees, texte)
        confiance_globale = (
            sum(c.confiance for c in clauses_notees) / len(clauses_notees) if clauses_notees else 0.0
        )

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
                tokens=tokens_entree + tokens_sortie,
                tokens_entree=tokens_entree,
                tokens_sortie=tokens_sortie,
                tronque=False,
            )
        )
        telemetry.logger.info(
            "analyse.terminee",
            version=bundle.version,
            request_id=rid,
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
        libelle=libeller(confiance_globale, bundle.parametres.get("seuils_libelle")),
        request_id=rid,
        modele=bundle.modele,
        version=bundle.version,
        sections=len(sections),
        appels_llm=len(sections),
        latence_ms=latence,
        cout_eur=round(cout_total, 6),
    )


def capturer_si_peu_sur(texte: str, reponse: "ReponseAnalyseV2", telemetry: Telemetry) -> None:
    """Brique 17 (Ch2) : une analyse peu sûre devient un candidat du jeu d'évaluation (masqué).
    Appelé par les routes, pas par ``analyser_v2`` : le gate d'évaluation ne doit rien capturer.
    Une panne de capture ne casse jamais la réponse au juriste : elle est journalisée."""
    try:
        from ops.enrichissement import capturer

        capturer(texte, request_id=reponse.request_id, version=reponse.version,
                 score=reponse.confiance_globale, clauses=[c.type for c in reponse.clauses])
    except Exception as exc:  # noqa: BLE001 — la capture est accessoire, la réponse ne l'est pas
        telemetry.logger.warning("capture.echec", request_id=reponse.request_id, cause=str(exc))


@router.post("/analyse", response_model=ReponseAnalyseV2)
def analyse(
    requete: RequeteAnalyseV2,
    response: Response,
    client: LLMClient = Depends(get_client_v2),
    telemetry: Telemetry = Depends(get_telemetry),
) -> ReponseAnalyseV2 | JSONResponse:
    rid = nouveau_request_id()
    if len(requete.texte) > TAILLE_MAX_TEXTE:
        # Refus AVANT tout appel au modèle : un document surdimensionné ne doit pouvoir
        # ni vider le budget ni allonger la file (red-team Era, 23/09 — drain du budget).
        return JSONResponse(
            status_code=413,
            content={"detail": f"document trop volumineux ({len(requete.texte)} caractères ; max {TAILLE_MAX_TEXTE})", "request_id": rid},
        )
    try:
        reponse = analyser_v2(requete.texte, client, telemetry, request_id=rid)
    except ErreurLLM as exc:
        # Succès comme échec, la réponse est signée (version) et corrélable (request_id).
        return JSONResponse(
            status_code=503,
            content={"detail": f"fournisseur LLM indisponible : {exc}", "request_id": rid},
            headers={"X-Mardik-Version": client.bundle.version},
        )
    capturer_si_peu_sur(requete.texte, reponse, telemetry)
    response.headers["X-Mardik-Version"] = reponse.version
    return reponse
