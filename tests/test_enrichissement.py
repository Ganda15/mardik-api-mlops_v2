"""Brique 17 (Chantier 2) — enrichir le jeu d'évaluation avec les cas réels à faible confiance.

Test 8 du brief : un cas de production à faible confiance, capturé, apparaît dans le jeu d'évaluation
et la chaîne le rejoue à la fusion suivante. Conception Ch2 §4.3 :
1. capture — une analyse dont le score global est < ``capture.score_global_max`` (0,5) est copiée
   dans ``ops/candidats.jsonl`` ;
2. masquage AVANT stockage — parties, montants, courriels remplacés ; partiel par construction, dit tel quel ;
3. étiquetage — un juriste dit quelles clauses étaient attendues ;
4. ajout — le cas entre dans ``eval/attendus.jsonl`` (+ son texte dans ``eval/contrats/``) : un commit ;
5. rejeu — la PR touche ``eval/attendus.jsonl`` : le filtre de chemin de llmops.yml relance le gate.
La capture est tracée dans ``candidats.jsonl`` ; le journal de pilotage trace l'``enrichissement`` (une décision),
sans jamais un texte de contrat.
"""
from __future__ import annotations

import json

import pytest

from ops.enrichissement import ErreurEnrichissement, ajouter_cas, capturer, masquer

TEXTE = (
    "Entre les soussignés : Mardik SAS, ci-après le Client, et Atelier Verrière SA, ci-après le Prestataire. "
    "Article 4 — Prix. Le Client verse un prix forfaitaire de 22 000 euros hors taxes, puis 1 500,50 € par mois. "
    "Contact : juridique@mardik.fr. Article 5 — Durée. Le présent contrat est conclu pour 24 mois."
)


def test_le_masquage_retire_parties_montants_et_courriels():
    m = masquer(TEXTE)
    for fuite in ("Mardik SAS", "Atelier Verrière SA", "22 000 euros", "1 500,50 €", "juridique@mardik.fr"):
        assert fuite not in m
    assert "PARTIE_A" in m and "PARTIE_B" in m and "MONTANT" in m and "COURRIEL" in m
    assert "Le présent contrat est conclu pour 24 mois." in m        # le fond juridique reste


def test_une_analyse_sure_n_est_pas_capturee(tmp_path, registry):
    chemin = tmp_path / "candidats.jsonl"
    assert capturer(TEXTE, request_id="req_1", version="v2.0.0", score=0.93, clauses=["durée"],
                    chemin=chemin) is False
    assert not chemin.exists()


def test_une_analyse_peu_sure_est_capturee_masquee_et_tracee(tmp_path, registry):
    chemin = tmp_path / "candidats.jsonl"
    assert capturer(TEXTE, request_id="req_2", version="v2.0.0", score=0.31, clauses=["durée"],
                    chemin=chemin) is True
    brut = chemin.read_text(encoding="utf-8")
    assert "Mardik SAS" not in brut and "22 000 euros" not in brut
    cas = json.loads(brut.splitlines()[0])
    assert cas["request_id"] == "req_2" and cas["score"] == 0.31 and cas["clauses_trouvees"] == ["durée"]
    assert cas["seuil"] == 0.5                                           # la trace dit pourquoi il est là
    # Le journal de pilotage garde les DÉCISIONS (alerte, promotion, rollback, enrichissement, seuil) ; une
    # capture est une observation, tracée dans candidats.jsonl. Constaté le 23/09 : journaliser chaque capture
    # cassait le test fourni test_promotion_canary_puis_totale (« chaque étape [de déploiement] est journalisée »).
    assert all(e["evenement"] != "capture" for e in registry.journal())


@pytest.fixture
def jeu(tmp_path, registry):
    candidats = tmp_path / "candidats.jsonl"
    capturer(TEXTE, request_id="req_3", version="v2.0.0", score=0.2, clauses=[], chemin=candidats)
    attendus = tmp_path / "attendus.jsonl"
    attendus.write_text('{"contrat_id": "c01", "clauses_attendues": ["durée"], "seuil_note": 0.75}\n', encoding="utf-8")
    contrats = tmp_path / "contrats"
    contrats.mkdir()
    return {"candidats": candidats, "attendus": attendus, "contrats": contrats, "registry": registry}


def test_un_cas_etiquete_entre_dans_le_jeu_d_evaluation(jeu):
    cid = ajouter_cas("req_3", ["durée", "prix et paiement"], **jeu)
    lignes = [json.loads(x) for x in jeu["attendus"].read_text(encoding="utf-8").splitlines()]
    assert [x["contrat_id"] for x in lignes] == ["c01", cid]
    assert lignes[-1]["clauses_attendues"] == ["durée", "prix et paiement"]
    assert lignes[-1]["origine"] == {"request_id": "req_3", "version": "v2.0.0", "score": 0.2}
    texte = (jeu["contrats"] / f"{cid}.txt").read_text(encoding="utf-8")
    assert "PARTIE_A" in texte and "Mardik SAS" not in texte
    e = jeu["registry"].journal()[-1]
    assert e["evenement"] == "enrichissement" and e["contrat_id"] == cid and e["nb_cas"] == 2


def test_un_type_de_clause_inconnu_est_refuse(jeu):
    with pytest.raises(ErreurEnrichissement, match="inconnu"):
        ajouter_cas("req_3", ["clause magique"], **jeu)


def test_un_candidat_absent_ou_deja_ajoute_est_refuse(jeu):
    with pytest.raises(ErreurEnrichissement, match="introuvable"):
        ajouter_cas("req_absent", ["durée"], **jeu)
    ajouter_cas("req_3", ["durée"], **jeu)
    with pytest.raises(ErreurEnrichissement, match="déjà"):
        ajouter_cas("req_3", ["durée"], **jeu)


def test_le_gate_rejoue_le_cas_ajoute(jeu, historique):
    """« Rejoué par le gate » : le gate évalue le nouveau cas comme les douze de référence."""
    from eval.run_eval import evaluer

    cid = ajouter_cas("req_3", ["durée"], **jeu)
    rapport = evaluer("v2", sous_ensemble=[cid], attendus=jeu["attendus"], contrats=jeu["contrats"],
                      historique=historique)
    assert cid in rapport.par_contrat


def test_une_requete_v2_peu_sure_est_capturee_par_l_api(client, tmp_path, monkeypatch):
    """Le branchement réel : la route /v2/analyse capture elle-même. Ce test prouve le BRANCHEMENT, pas le
    score du faux modèle : un seuil de capture à 1,01 (fichier de démo) rend toute analyse « peu sûre »."""
    import yaml

    from ops.seuils import charger_seuils

    s = charger_seuils()
    s["capture"]["score_global_max"] = 1.01
    (tmp_path / "seuils.yml").write_text(yaml.safe_dump(s, allow_unicode=True), encoding="utf-8")
    monkeypatch.setenv("MARDIK_SEUILS", str(tmp_path / "seuils.yml"))
    monkeypatch.setenv("CANDIDATS_PATH", str(tmp_path / "candidats-api.jsonl"))
    corps = client.post("/v2/analyse", json={"texte": TEXTE}).json()
    cas = [json.loads(x) for x in (tmp_path / "candidats-api.jsonl").read_text(encoding="utf-8").splitlines()]
    assert cas[-1]["request_id"] == corps["request_id"]
