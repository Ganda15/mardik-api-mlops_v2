"""Brique 17 bis — les cas de production ont leur propre fichier, rejoués par leur propre étape.

Trouvé le 23/09 en versant le premier cas réel : le test fourni ``test_gate_evaluation_note_par_version``
fige « les 12 contrats annotés » (``set(par_contrat) == {c01…c12}``). Un cas de production ajouté à
``eval/attendus.jsonl`` casse ce test — pour toujours, pas seulement à la fusion suivante. Donc :
- ``eval/attendus.jsonl`` : les 12 contrats de référence, intouchés ;
- ``eval/attendus_production.jsonl`` : les cas venus de la production (brique 17) ;
- ``python -m eval.rejouer_production`` : les rejoue seuls, et bloque la chaîne s'ils échouent (test 8 du brief).
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from eval.rejouer_production import main, rejouer
from eval.run_eval import evaluer
from ops.enrichissement import ajouter_cas, capturer

RACINE = Path(__file__).resolve().parent.parent
CLAUSES_C02 = ["durée", "prix et paiement", "pénalité de retard", "garantie", "résiliation", "droit applicable"]


@pytest.fixture
def production(tmp_path, registry, monkeypatch):
    """Un cas de production étiqueté, dans SON fichier (jamais eval/attendus.jsonl)."""
    candidats = tmp_path / "candidats.jsonl"
    texte = (RACINE / "eval" / "contrats" / "c02.txt").read_text(encoding="utf-8")   # le vrai cas du 23/09
    capturer(texte, request_id="req_p1", version="v2.0.0", score=0.3, clauses=[], chemin=candidats)
    attendus = tmp_path / "attendus_production.jsonl"
    contrats = tmp_path / "contrats"
    monkeypatch.setenv("ATTENDUS_PRODUCTION_PATH", str(attendus))

    def _ajouter(clauses):
        return ajouter_cas("req_p1", clauses, candidats=candidats, contrats=contrats, registry=registry)

    return {"ajouter": _ajouter, "attendus": attendus, "contrats": contrats}


def test_sans_cas_de_production_le_rejeu_ne_fait_rien(tmp_path, historique, monkeypatch):
    monkeypatch.setenv("ATTENDUS_PRODUCTION_PATH", str(tmp_path / "absent.jsonl"))
    assert rejouer("v2", historique=historique) is None
    assert main(["--version", "v2", "--historique", str(historique)]) == 0
    assert not historique.exists()


def test_le_rejeu_evalue_seulement_les_cas_de_production(production, historique):
    cid = production["ajouter"](CLAUSES_C02)
    rapport = rejouer("v2", contrats=production["contrats"], historique=historique)
    assert set(rapport.par_contrat) == {cid}
    assert rapport.passe, rapport.motifs


def test_le_gate_par_defaut_reste_sur_les_12_contrats_de_reference(production, historique):
    """L'invariant du test fourni : un cas de production ne change jamais ce que le gate voit par défaut."""
    production["ajouter"](["durée"])
    rapport = evaluer("v2", historique=historique)
    assert set(rapport.par_contrat) == {f"c{i:02d}" for i in range(1, 13)}


def test_un_cas_de_production_en_echec_bloque_la_chaine(production, historique):
    production["ajouter"](["force majeure", "propriété intellectuelle", "confidentialité"])   # absentes du texte
    rapport = rejouer("v2", contrats=production["contrats"], historique=historique)
    assert not rapport.passe
    assert main(["--version", "v2", "--contrats", str(production["contrats"]), "--historique", str(historique)]) == 1


def test_la_chaine_rejoue_les_cas_de_production_dans_le_job_du_gate():
    texte = (RACINE / ".github" / "workflows" / "llmops.yml").read_text(encoding="utf-8")
    wf = yaml.safe_load(texte)
    filtres = wf["jobs"]["filtre-chemins"]["steps"][1]["with"]["filters"]
    assert "eval/attendus_production.jsonl" in filtres                   # la PR qui ajoute un cas relance le gate
    etapes = [s.get("run", "") for s in wf["jobs"]["gate-evaluation"]["steps"]]
    assert any("eval.rejouer_production" in r for r in etapes)           # et le rejeu tourne à chaque fusion
