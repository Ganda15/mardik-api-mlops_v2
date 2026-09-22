"""Tests unitaires du score composite — brique 5 du Chantier 1 (aucune dépendance au LLM).

scorer() doit ramener à 0 une citation inventée, quelle que soit la confiance déclarée par le
modèle : c'est le garde-fou central de cette brique. Voir docs/spec-v2-perimetre.md §7, brique 5.
"""
from __future__ import annotations

from app.pipeline.confiance import Clause, scorer


def test_extrait_verifie_donne_le_score_du_modele_en_une_seule_section():
    texte = "Article 1 — Objet\n\nLe présent contrat a pour objet la fourniture de services."
    clause = Clause(
        type="objet", extrait="a pour objet la fourniture de services", confiance_llm=0.8, sections=[0]
    )
    scored, score_global = scorer([clause], texte)
    assert scored[0].confiance == 0.8
    assert score_global == 0.8


def test_extrait_invente_est_ramene_a_zero_meme_avec_haute_confiance_declaree():
    texte = "Article 1 — Objet\n\nLe présent contrat a pour objet la fourniture de services."
    clause = Clause(
        type="objet", extrait="une phrase qui n'existe pas dans le contrat", confiance_llm=0.99, sections=[0]
    )
    scored, _ = scorer([clause], texte)
    assert scored[0].confiance == 0.0


def test_bonus_multi_sections_plafonne_a_1():
    texte = "Le prix est de 1000 euros. Le prix est payable a 30 jours."
    clause = Clause(type="prix", extrait="Le prix est de 1000 euros", confiance_llm=0.98, sections=[0, 3])
    scored, _ = scorer([clause], texte)
    assert scored[0].confiance == 1.0  # 0.98 + le bonus dépasse 1.0 : plafonné


def test_score_global_est_la_moyenne_des_scores_par_clause():
    texte = "Le prix est de 1000 euros. La duree est de 12 mois."
    c1 = Clause(type="prix", extrait="Le prix est de 1000 euros", confiance_llm=0.8, sections=[0])
    c2 = Clause(type="durée", extrait="La duree est de 12 mois", confiance_llm=0.6, sections=[0])
    scored, score_global = scorer([c1, c2], texte)
    assert score_global == (0.8 + 0.6) / 2


def test_aucune_clause_donne_un_score_global_de_zero():
    scored, score_global = scorer([], "peu importe le texte")
    assert scored == []
    assert score_global == 0.0


def test_extrait_vide_nest_jamais_considere_verifie():
    # piège Python : "" in texte vaut toujours True sans le garde explicite
    clause = Clause(type="durée", extrait="", confiance_llm=0.9, sections=[0])
    scored, _ = scorer([clause], "n'importe quel texte, meme non vide")
    assert scored[0].confiance == 0.0
