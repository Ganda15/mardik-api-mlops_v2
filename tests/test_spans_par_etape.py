"""Un span par étape du pipeline, et la décision de routage de la gateway — séance du 25/09 :
« tout le travail de télémétrie… pour une ligne de code » ; « du début à la fin, avec les spans parents et enfants ».

Avant : 2 types de span (analyse.requete, llm.appel). Le découpage, la consolidation, la notation, la calibration et
le choix de version de la gateway ne laissaient aucune trace mesurable dans Jaeger.
"""
from __future__ import annotations

import yaml

from tests.conftest import RACINE

ETAPES = ["pipeline.decoupage", "pipeline.consolidation", "pipeline.notation", "pipeline.calibration"]
MARQUEUR = "Clause-temoin-ZQ77 : ce texte ne doit jamais devenir un attribut de span."


def _spans(exporter):
    return {s.name: s for s in exporter.get_finished_spans()}


def test_chaque_etape_est_un_span_enfant_de_l_analyse(client, span_exporter, contrat):
    client.post("/v2/analyse", json={"texte": contrat("c01")})
    spans = _spans(span_exporter)
    racine = spans["analyse.requete"]
    for nom in ETAPES:
        assert nom in spans, nom
        assert spans[nom].parent is not None and spans[nom].parent.span_id == racine.context.span_id, nom
        assert spans[nom].context.trace_id == racine.context.trace_id, nom


def test_les_etapes_portent_leurs_mesures(client, span_exporter, contrat):
    r = client.post("/v2/analyse", json={"texte": contrat("c01")}).json()
    spans = _spans(span_exporter)
    assert spans["pipeline.decoupage"].attributes["mardik.sections"] == r["sections"]
    assert spans["pipeline.decoupage"].attributes["mardik.caracteres"] == len(contrat("c01"))
    assert spans["pipeline.consolidation"].attributes["mardik.clauses_consolidees"] >= len(r["clauses"])
    assert spans["pipeline.notation"].attributes["mardik.clauses_prouvees"] == len(r["clauses"])
    assert spans["pipeline.notation"].attributes["mardik.confiance_globale"] == r["confiance_globale"]
    assert spans["pipeline.calibration"].attributes["mardik.calibration"] == "platt"


def test_ordre_decoupage_puis_appels_puis_notation(client, span_exporter, contrat):
    client.post("/v2/analyse", json={"texte": contrat("c01")})
    tous = span_exporter.get_finished_spans()
    decoupage = next(s for s in tous if s.name == "pipeline.decoupage")
    notation = next(s for s in tous if s.name == "pipeline.notation")
    appels = [s for s in tous if s.name == "llm.appel"]
    assert appels
    assert decoupage.end_time <= min(a.start_time for a in appels)
    assert notation.start_time >= max(a.end_time for a in appels)


def test_la_gateway_trace_sa_decision_de_routage(client, span_exporter, contrat):
    reponse = client.post("/analyse", json={"texte": contrat("c01")})
    spans = _spans(span_exporter)
    racine, routage, analyse = spans["gateway.requete"], spans["gateway.routage"], spans["analyse.requete"]
    assert racine.parent is None
    assert routage.parent.span_id == racine.context.span_id
    assert analyse.parent.span_id == racine.context.span_id  # un seul arbre, du début à la fin
    a = routage.attributes
    assert a["gateway.version_servie"] == reponse.headers["X-Mardik-Version"]
    assert 0 <= a["gateway.tirage"] <= 100
    assert "gateway.canary_percent" in a and "gateway.active" in a
    assert racine.attributes["mardik.request_id"].startswith("req_")


def test_aucun_texte_de_contrat_dans_les_attributs(client, span_exporter, contrat):
    # RGPD : un contrat peut contenir des données personnelles ; seuls des identifiants et des mesures sont tracés.
    client.post("/analyse", json={"texte": contrat("c01") + "\n\n" + MARQUEUR})
    client.post("/v2/analyse", json={"texte": contrat("c01") + "\n\n" + MARQUEUR})
    for s in span_exporter.get_finished_spans():
        assert all("ZQ77" not in str(v) for v in (s.attributes or {}).values()), s.name


def test_le_filtre_des_evals_couvre_le_code_sensible():
    # Séance du 25/09 : toute branche (correctif compris) qui touche le modèle, le prompt ou les évals relance le gate.
    flux = yaml.safe_load((RACINE / ".github" / "workflows" / "llmops.yml").read_text(encoding="utf-8"))
    filtre = next(e for e in flux["jobs"]["filtre-chemins"]["steps"] if e.get("id") == "filtre")
    chemins = yaml.safe_load(filtre["with"]["filters"])["gate"]
    for sensible in ("models/v2/config.yaml", "prompts/**", "app/pipeline/**", "eval/*.py",
                     "app/llm_client.py", "app/api_v2.py"):
        assert sensible in chemins, sensible
    declencheurs = flux.get("on") or flux.get(True) or {}  # PyYAML lit la clé « on » comme le booléen True
    assert "pull_request" in declencheurs
    assert "branches" not in (declencheurs["pull_request"] or {}), \
        "le gate des PR ne doit filtrer aucune branche (fix/*, hotfix/* compris)"


def test_la_commande_tracer_montre_l_arbre_par_indentation(tmp_path):
    from ops.tracer import _afficher

    trace = [
        {"nom": "gateway.requete", "span_id": "a", "parent_id": None, "debut": 1.0, "duree_ms": 10.0, "statut": "UNSET", "attributs": {}},
        {"nom": "analyse.requete", "span_id": "b", "parent_id": "a", "debut": 1.1, "duree_ms": 8.0, "statut": "UNSET", "attributs": {}},
        {"nom": "llm.appel", "span_id": "c", "parent_id": "b", "debut": 1.2, "duree_ms": 5.0, "statut": "UNSET", "attributs": {}},
    ]
    sortie = _afficher({"request_id": "req_x", "metriques": None, "trace": trace, "journaux": [], "manifeste": None,
                        "seuils": {}, "decisions": []}).splitlines()
    retrait = {nom: next(len(ligne) - len(ligne.lstrip()) for ligne in sortie if ligne.strip().startswith(nom))
               for nom in ("gateway.requete", "analyse.requete", "llm.appel")}
    assert retrait["gateway.requete"] < retrait["analyse.requete"] < retrait["llm.appel"]
