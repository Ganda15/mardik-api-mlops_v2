"""Traçabilité : retrouver l'historique complet d'une analyse à partir de son ``request_id`` —
quelle version a répondu, quel modèle, combien de temps, quels seuils, quelle décision.

Deux manques fermés ici (24/09) :
* la ligne de ``ops/metrics.jsonl`` ne portait pas le ``request_id`` → impossible de la relier à une réponse ;
* traces et journaux partaient sur la console → perdus à l'arrêt du processus.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import api_v1, api_v2, gateway
from app.llm_client import ErreurLLM
from app.main import create_app
from app.telemetry import FichierSpanExporter, Mesure, MetricsStore, build_telemetry

MARQUEUR = "Clause-temoin-XK42 : ce texte ne doit jamais sortir du processus."


def _lignes(chemin: Path) -> list[dict]:
    return [json.loads(ligne) for ligne in chemin.read_text(encoding="utf-8").splitlines() if ligne.strip()]


@pytest.fixture
def telemetrie_fichiers(tmp_path: Path):
    return build_telemetry(
        span_exporter=FichierSpanExporter(tmp_path / "traces.jsonl"),
        metrics_path=tmp_path / "metrics.jsonl",
        logs_path=tmp_path / "logs.jsonl",
    )


@pytest.fixture
def client_fichiers(telemetrie_fichiers, registry) -> TestClient:
    app = create_app()
    for module in (api_v1, api_v2, gateway):
        app.dependency_overrides[module.get_telemetry] = lambda: telemetrie_fichiers
    app.dependency_overrides[gateway.get_registry] = lambda: registry
    return TestClient(app)


# --- Manque 1 : la ligne de métriques porte le request_id ---------------------------------------

def test_ligne_de_metriques_porte_le_request_id(client, tmp_path, contrat):
    rid = client.post("/v2/analyse", json={"texte": contrat("c01")}).json()["request_id"]
    lignes = _lignes(tmp_path / "metrics.jsonl")
    assert [ligne["request_id"] for ligne in lignes] == [rid]


def test_ligne_de_metriques_d_un_echec_porte_le_request_id(client, tmp_path, contrat, monkeypatch):
    def panne(*_a, **_k):
        raise ErreurLLM("fournisseur injoignable")

    monkeypatch.setattr(api_v2, "extraire", panne)
    r = client.post("/v2/analyse", json={"texte": contrat("c01")})
    assert r.status_code == 503
    ligne = _lignes(tmp_path / "metrics.jsonl")[-1]
    assert ligne["erreur"] is True and ligne["request_id"] == r.json()["request_id"]


def test_anciennes_lignes_sans_request_id_restent_lisibles(tmp_path):
    # Les fichiers écrits avant ce changement n'ont pas le champ : le tableau de bord et le watcher les lisent encore.
    chemin = tmp_path / "metrics.jsonl"
    chemin.write_text(json.dumps({"ts": 1.0, "version": "v2.6.0", "route": "/v2/analyse", "latence_ms": 5.0}) + "\n",
                      encoding="utf-8")
    [m] = MetricsStore(chemin).lire()
    assert m.request_id is None and m.version == "v2.6.0"


# --- Manque 2 : traces et journaux conservés sur disque -----------------------------------------

def test_trace_conservee_sur_disque_avec_parent_et_appels_llm(client_fichiers, tmp_path, contrat):
    rid = client_fichiers.post("/v2/analyse", json={"texte": contrat("c01")}).json()["request_id"]
    spans = _lignes(tmp_path / "traces.jsonl")
    [racine] = [s for s in spans if s["nom"] == "analyse.requete"]
    appels = [s for s in spans if s["nom"] == "llm.appel"]
    assert racine["attributs"]["mardik.request_id"] == rid
    assert appels and all(a["trace_id"] == racine["trace_id"] and a["parent_id"] == racine["span_id"] for a in appels)
    assert all(a["duree_ms"] >= 0 and "llm.latence_ms" in a["attributs"] for a in appels)


def test_journaux_conserves_sur_disque(client_fichiers, tmp_path, contrat):
    rid = client_fichiers.post("/v2/analyse", json={"texte": contrat("c01")}).json()["request_id"]
    evenements = [e for e in _lignes(tmp_path / "logs.jsonl") if e.get("request_id") == rid]
    assert [e["event"] for e in evenements] == ["analyse.terminee"]
    assert evenements[0]["latence_ms"] > 0


def test_le_texte_du_contrat_ne_sort_jamais_dans_traces_ni_journaux(client_fichiers, tmp_path, contrat):
    # RGPD : un contrat peut contenir des données personnelles ; seuls des identifiants et des mesures sont tracés.
    client_fichiers.post("/v2/analyse", json={"texte": contrat("c01") + "\n\n" + MARQUEUR})
    for nom in ("traces.jsonl", "logs.jsonl", "metrics.jsonl"):
        assert "XK42" not in (tmp_path / nom).read_text(encoding="utf-8"), nom


def test_mode_par_defaut_ecrit_les_traces_dans_un_fichier(tmp_path, monkeypatch):
    from app import telemetry as t

    monkeypatch.delenv("OTEL_TRACES", raising=False)
    monkeypatch.setenv("TRACES_PATH", str(tmp_path / "traces.jsonl"))
    monkeypatch.setenv("LOGS_PATH", str(tmp_path / "logs.jsonl"))
    monkeypatch.setattr(t, "_defaut", None)
    tel = t.build_default_telemetry()
    with tel.tracer.start_as_current_span("essai"):
        pass
    assert [s["nom"] for s in _lignes(tmp_path / "traces.jsonl")] == ["essai"]
    monkeypatch.setattr(t, "_defaut", None)


def test_modes_combinables_otlp_et_fichier(monkeypatch, tmp_path):
    from app import telemetry as t

    monkeypatch.setenv("TRACES_PATH", str(tmp_path / "traces.jsonl"))
    exporteurs = t.exporteurs_depuis_mode("otlp,fichier")
    assert [type(e).__name__ for e in exporteurs] == ["OTLPSpanExporter", "FichierSpanExporter"]
    assert t.exporteurs_depuis_mode("off") == []


# --- La preuve : une commande reconstitue l'historique complet ----------------------------------

def test_tracer_reconstitue_l_historique_complet(client_fichiers, tmp_path, contrat, registry):
    from ops.tracer import historique

    reponse = client_fichiers.post("/v2/analyse", json={"texte": contrat("c01")})
    rid = reponse.json()["request_id"]
    h = historique(rid, metrics=tmp_path / "metrics.jsonl", traces=tmp_path / "traces.jsonl",
                   logs=tmp_path / "logs.jsonl", registre=registry.root)
    assert h["metriques"]["request_id"] == rid
    assert h["metriques"]["version"] == reponse.headers["X-Mardik-Version"]
    assert {s["nom"] for s in h["trace"]} >= {"analyse.requete", "llm.appel"}
    assert [e["event"] for e in h["journaux"]] == ["analyse.terminee"]
    assert "seuils_libelle" in h["seuils"]


def test_tracer_request_id_inconnu(tmp_path):
    from ops.tracer import historique

    h = historique("inconnu", metrics=tmp_path / "m.jsonl", traces=tmp_path / "t.jsonl",
                   logs=tmp_path / "l.jsonl", registre=tmp_path / "registry")
    assert h["metriques"] is None and h["trace"] == [] and h["journaux"] == []


def test_mesure_accepte_le_request_id():
    assert Mesure(ts=0.0, version="v", route="/r", latence_ms=1.0, request_id="abc").to_dict()["request_id"] == "abc"


def test_commande_tracer_affiche_les_six_rubriques(client_fichiers, tmp_path, contrat, registry, monkeypatch, capsys):
    from ops import tracer

    rid = client_fichiers.post("/v2/analyse", json={"texte": contrat("c01")}).json()["request_id"]
    for var, nom in (("METRICS_PATH", "metrics.jsonl"), ("TRACES_PATH", "traces.jsonl"), ("LOGS_PATH", "logs.jsonl")):
        monkeypatch.setenv(var, str(tmp_path / nom))
    monkeypatch.setenv("REGISTRY_PATH", str(registry.root))
    assert tracer.main([rid]) == 0
    sortie = capsys.readouterr().out
    for rubrique in ("[1] Métriques", "[2] Trace", "llm.appel", "[3] Journaux : analyse.terminee",
                     "[4] Manifeste", "[5] Seuils", "[6] Décisions"):
        assert rubrique in sortie, rubrique
    assert tracer.main(["inconnu"]) == 1
    assert "introuvable" in capsys.readouterr().out


def test_trace_porte_le_modele_reellement_appele(client_fichiers, tmp_path, contrat):
    # Le manifeste dit quel modèle la version VISAIT ; la trace dit lequel a répondu À CETTE requête.
    client_fichiers.post("/v2/analyse", json={"texte": contrat("c01")})
    [racine] = [s for s in _lignes(tmp_path / "traces.jsonl") if s["nom"] == "analyse.requete"]
    assert racine["attributs"]["llm.modele"] == "modele-de-test"


def test_seuils_lus_dans_la_config_du_commit_de_la_version():
    # v2.0.0 n'avait pas de calibration : afficher la config du jour serait faux.
    from ops.tracer import _seuils

    configs = {("f4706ba", "models/v2/config.yaml"): "parametres:\n  seuils_libelle: {haute: 0.9}\n"}
    s = _seuils("v2.0.0", "f4706ba", lire=lambda commit, chemin: configs.get((commit, chemin)))
    assert s == {"seuils_libelle": {"haute": 0.9}, "source": "commit f4706ba"}


def test_seuils_commit_illisible_le_dit():
    from ops.tracer import _seuils

    s = _seuils("v2.0.0", "absent", lire=lambda commit, chemin: None)
    assert s["source"].startswith("config actuelle")
