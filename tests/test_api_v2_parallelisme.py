"""Brique 12 — les sections sont analysées en parallèle, pas l'une après l'autre.

Constat du 21/09 (Jaeger, vrai modèle, contrat c01) : 18 sections traitées en série à
22,7 s de moyenne = ~6 minutes par analyse, contre 8 s exigées par le client. Les sections
sont indépendantes : rien n'impose la série. Ce test le fige : avec un client qui met
``DELAI`` par appel, N sections doivent coûter ~``DELAI``, pas N × ``DELAI``.
"""
from __future__ import annotations

import json
import threading
import time

from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.api_v2 import analyser_v2
from app.llm_client import Bundle, ReponseLLM
from app.telemetry import Telemetry

DELAI = 0.3
NB_SECTIONS = 6
TYPES = ["résiliation", "confidentialité", "force majeure", "garantie", "exclusivité", "durée"]


class ClientLent:
    """Un faux fournisseur : chaque appel dort DELAI puis renvoie une clause valide.

    La clause renvoyée reprend la 1re ligne du texte de la section, pour que ``scorer``
    la retrouve dans le contrat ; le type dépend du titre, pour vérifier l'ordre.
    """

    def __init__(self, parallelisme: int | None = None) -> None:
        self.bundle = Bundle.charger("v2")
        if parallelisme is not None:
            self.bundle.parametres["parallelisme"] = parallelisme
        self.simultanes = 0
        self.pic_simultanes = 0
        self._verrou = threading.Lock()

    def completer(self, prompt_utilisateur: str, *, json_mode: bool = False) -> ReponseLLM:
        with self._verrou:
            self.simultanes += 1
            self.pic_simultanes = max(self.pic_simultanes, self.simultanes)
        try:
            time.sleep(DELAI)
        finally:
            with self._verrou:
                self.simultanes -= 1
        titre, _, texte = prompt_utilisateur.removeprefix("Titre : ").partition("\n\n")
        type_clause = TYPES[int(titre.split()[-1])]
        extrait = texte.strip().splitlines()[0]
        return ReponseLLM(
            texte=json.dumps({"clauses": [{"type": type_clause, "extrait": extrait, "confiance": 0.9}]}),
            latence_ms=DELAI * 1000,
            tokens_entree=50,
            tokens_sortie=30,
            mock=True,
        )

    def cout_eur(self, reponse: ReponseLLM) -> float:
        return 0.001


def _contrat() -> str:
    articles = []
    for i in range(NB_SECTIONS):
        articles.append(f"Article {i + 1} — Section {i}\n\nClause numero {i} du contrat de test.\n")
    return "\n".join(articles)


def test_les_sections_sont_analysees_en_parallele(
    telemetry: Telemetry, span_exporter: InMemorySpanExporter
) -> None:
    client = ClientLent(parallelisme=NB_SECTIONS)

    debut = time.perf_counter()
    resultat = analyser_v2(_contrat(), client, telemetry)
    duree = time.perf_counter() - debut

    assert resultat.sections == NB_SECTIONS
    assert resultat.appels_llm == NB_SECTIONS
    # Le vrai test : N appels de DELAI chacun ne doivent pas coûter N × DELAI.
    assert duree < 2 * DELAI, f"{duree:.2f}s pour {NB_SECTIONS} sections de {DELAI}s : c'est de la série"
    assert client.pic_simultanes > 1

    # L'ordre des sections est conservé malgré le parallélisme.
    par_type = {c.type: c for c in resultat.clauses}
    for i, type_clause in enumerate(TYPES):
        assert par_type[type_clause].sections == [i]

    # Chaque llm.appel reste enfant de analyse.requete (sinon Jaeger perd la cascade).
    spans = span_exporter.get_finished_spans()
    racine = next(s for s in spans if s.name == "analyse.requete")
    appels = [s for s in spans if s.name == "llm.appel"]
    assert len(appels) == NB_SECTIONS
    assert all(s.parent is not None and s.parent.span_id == racine.context.span_id for s in appels)


def test_parallelisme_1_reste_sequentiel(telemetry: Telemetry) -> None:
    client = ClientLent(parallelisme=1)

    debut = time.perf_counter()
    resultat = analyser_v2(_contrat(), client, telemetry)
    duree = time.perf_counter() - debut

    assert resultat.sections == NB_SECTIONS
    assert duree >= NB_SECTIONS * DELAI
    assert client.pic_simultanes == 1
