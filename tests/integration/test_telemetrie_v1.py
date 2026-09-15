"""Tests d'intégration hérités du brief de remédiation — [FOURNI], verts.

Ils vérifient que le tracing et les métriques posés à la remédiation sont bien
en place sur la v1. Les apprenants construisent dessus (la v2 et la gateway
doivent produire les mêmes signaux).
"""
from __future__ import annotations

from structlog.testing import capture_logs

from app.api_v1 import analyser_v1
from app.llm_client import Bundle, LLMClient


def _analyser(telemetry, texte="Article 1 — Résiliation\n\nChaque partie peut résilier le contrat. " * 3):
    return analyser_v1(texte, LLMClient(Bundle.charger("v1")), telemetry)


def test_v1_repond_et_analyse_un_contrat(telemetry, contrat):
    reponse = _analyser(telemetry, contrat("c01"))
    assert reponse.version == "v1.0.0"
    assert "résiliation" in reponse.clauses
    assert reponse.tronque is False


def test_v1_tronque_les_contrats_longs(telemetry, contrat):
    reponse = _analyser(telemetry, contrat("c07"))
    assert reponse.tronque is True, "la douleur de départ doit être réelle"


def test_appel_llm_trace_dans_la_requete(telemetry, span_exporter):
    _analyser(telemetry)
    spans = {s.name: s for s in span_exporter.get_finished_spans()}
    assert {"analyse.requete", "llm.appel"} <= set(spans)
    assert spans["llm.appel"].context.trace_id == spans["analyse.requete"].context.trace_id
    assert spans["analyse.requete"].attributes["mardik.version"] == "v1.0.0"


def test_metrique_de_latence_journalisee(telemetry, metriques):
    _analyser(telemetry)
    mesures = metriques.lire()
    assert len(mesures) == 1
    m = mesures[0]
    assert m.version == "v1.0.0" and m.route == "/v1/analyse"
    assert m.latence_ms >= 0 and m.erreur is False and m.appels_llm == 1


def test_journal_structure_en_fin_de_requete(telemetry):
    with capture_logs() as logs:
        _analyser(telemetry)
    evenements = [entree.get("event") for entree in logs]
    assert "analyse.terminee" in evenements


def test_echec_fournisseur_journalise_une_erreur(telemetry, metriques, monkeypatch):
    import pytest

    from app.llm_client import ErreurLLM

    monkeypatch.setenv("MOCK", "off")
    monkeypatch.setenv("LLM_PROXY_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("LLM_TIMEOUT_S", "2")
    with pytest.raises(ErreurLLM):
        _analyser(telemetry)
    mesures = metriques.lire()
    assert mesures and mesures[-1].erreur is True
