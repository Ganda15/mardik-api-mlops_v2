"""Tests unitaires de la consolidation — brique 4 du Chantier 1 (aucune dépendance au LLM).

consolider() est la phase *reduce* du map-reduce : fusionne les clauses trouvées section par
section en une seule liste, sans jamais deux clauses du même type. Voir
docs/spec-v2-perimetre.md §7, brique 4.
"""
from __future__ import annotations

from app.pipeline.confiance import Clause
from app.pipeline.consolidation import consolider


def _clause(type_, extrait, confiance_llm, sections):
    return Clause(type=type_, extrait=extrait, confiance_llm=confiance_llm, sections=sections)


def test_aucun_doublon_types_distincts_passent_tels_quels():
    par_section = [
        [_clause("durée", "extrait durée", 0.9, [0])],
        [_clause("résiliation", "extrait résiliation", 0.8, [1])],
    ]
    resultat = consolider(par_section)
    assert [c.type for c in resultat] == ["durée", "résiliation"]


def test_meme_type_dans_deux_sections_devient_une_seule_clause():
    par_section = [
        [_clause("résiliation", "extrait court", 0.6, [0])],
        [_clause("résiliation", "extrait beaucoup plus long et détaillé", 0.9, [2])],
    ]
    resultat = consolider(par_section)
    assert len(resultat) == 1
    fusion = resultat[0]
    assert fusion.type == "résiliation"
    assert fusion.extrait == "extrait beaucoup plus long et détaillé"  # le plus informatif
    assert fusion.confiance_llm == 0.9  # la plus haute déclarée
    assert fusion.sections == [0, 2]  # fusionnées


def test_jamais_deux_clauses_du_meme_type_dans_le_resultat():
    par_section = [
        [_clause("garantie", "a", 0.5, [0])],
        [_clause("garantie", "bb", 0.6, [1])],
        [_clause("garantie", "ccc", 0.7, [2])],
    ]
    resultat = consolider(par_section)
    assert len(resultat) == 1
    assert resultat[0].sections == [0, 1, 2]
    assert resultat[0].extrait == "ccc"
    assert resultat[0].confiance_llm == 0.7


def test_ordre_de_sortie_suit_la_premiere_apparition():
    par_section = [
        [_clause("garantie", "g0", 0.5, [0])],
        [_clause("durée", "d1", 0.5, [1]), _clause("garantie", "g1", 0.5, [1])],
        [_clause("résiliation", "r2", 0.5, [2])],
    ]
    resultat = consolider(par_section)
    # "garantie" vue en premier (section 0), puis "durée" (section 1), puis "résiliation" (section 2)
    assert [c.type for c in resultat] == ["garantie", "durée", "résiliation"]


def test_entree_vide_donne_une_liste_vide():
    assert consolider([]) == []
    assert consolider([[], []]) == []
