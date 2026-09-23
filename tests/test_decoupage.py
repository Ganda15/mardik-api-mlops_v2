"""Tests unitaires du découpage — brique 2 du Chantier 1 (aucune dépendance au LLM).

Garantie centrale, testée directement : aucun caractère du contrat n'est perdu au découpage —
c'est précisément le défaut que la v1 ne corrige pas au-delà de son plafond. Voir
docs/spec-v2-perimetre.md §7, brique 2.
"""
from __future__ import annotations

from pathlib import Path

from app.pipeline.decoupage import decouper

RACINE = Path(__file__).resolve().parent.parent
CONTRATS = RACINE / "eval" / "contrats"


def _lire(cid: str) -> str:
    return (CONTRATS / f"{cid}.txt").read_text(encoding="utf-8")


def test_reconstruction_exacte_contrat_court():
    texte = _lire("c01")
    sections = decouper(texte, taille_max=100_000)
    assert "".join(s.texte for s in sections) == texte


def test_reconstruction_exacte_contrat_long():
    texte = _lire("c12")
    sections = decouper(texte, taille_max=100_000)
    assert "".join(s.texte for s in sections) == texte


def test_preambule_en_premiere_section():
    sections = decouper(_lire("c01"), taille_max=100_000)
    assert sections[0].indice == 0
    assert sections[0].titre == "préambule"
    assert "Préambule" in sections[0].texte


def test_titres_des_articles_extraits_sans_le_prefixe():
    sections = decouper(_lire("c12"), taille_max=100_000)
    titres = {s.titre for s in sections}
    assert "Résiliation" in titres
    assert "Droit applicable et juridiction" in titres
    # le préfixe "Article N —" ne doit pas rester dans le titre
    assert not any(t.lower().startswith("article") for t in titres)


def test_grand_taille_max_une_section_par_article_plus_preambule_c01():
    sections = decouper(_lire("c01"), taille_max=100_000)
    # c01 : préambule + 17 articles, aucun n'excède 100 000 caractères
    assert len(sections) == 18


def test_grand_taille_max_une_section_par_article_plus_preambule_c12():
    sections = decouper(_lire("c12"), taille_max=100_000)
    # c12 : préambule + 24 articles, aucune coupure supplémentaire attendue
    assert len(sections) == 25


def test_petit_taille_max_force_le_decoupage_sans_depasser_la_limite():
    sections = decouper(_lire("c12"), taille_max=2000)
    assert len(sections) > 25, "un article plus long que 2000 caractères doit être re-découpé"
    for s in sections:
        assert len(s.texte) <= 2000, f"section {s.indice} ({s.titre!r}) dépasse taille_max"
    # toujours rien de perdu, même après re-découpage
    assert "".join(s.texte for s in sections) == _lire("c12")


def test_le_decoupage_ne_coupe_jamais_une_phrase_en_deux():
    # une seule ligne (\n, pas \n\n) entre le titre et le corps : aucune frontière de
    # paragraphe dans le bloc, pour isoler la frontière de phrase que ce test vérifie
    texte = (
        "Article 1 — Test\n"
        "Premiere phrase courte. Deuxieme phrase courte. Troisieme phrase plus longue "
        "qui sert a remplir de l'espace pour forcer une coupure au bon endroit. "
        "Quatrieme phrase. Cinquieme et derniere phrase du paragraphe.\n"
    )
    # 150 : au-dessus de la plus longue phrase du texte (99 car., "Troisieme phrase…")
    # pour que le test vérifie la frontière de phrase, pas le repli de dernier recours
    sections = decouper(texte, taille_max=150)
    assert len(sections) > 1, "le test doit réellement forcer une coupure"
    assert "".join(s.texte for s in sections) == texte
    for s in sections[:-1]:
        fin = s.texte.rstrip()
        assert fin.endswith((".", "!", "?")), (
            f"la section {s.indice} se termine au milieu d'une phrase : {fin[-40:]!r}"
        )


def test_phrase_plus_longue_que_taille_max_utilise_le_repli_documente():
    # cas limite assumé : aucune coupure ne peut éviter le milieu d'une phrase si la
    # phrase elle-même dépasse taille_max — la garantie qui reste vraie est
    # len(texte) <= taille_max et la reconstruction exacte, jamais un crash
    phrase_longue = "Troisieme phrase plus longue qui sert a remplir de l'espace pour forcer une coupure au bon endroit."
    assert len(phrase_longue) > 90, "le texte du test doit rester plus long que taille_max"
    texte = f"Article 1 — Test\n{phrase_longue}\n"

    sections = decouper(texte, taille_max=90)

    assert "".join(s.texte for s in sections) == texte
    for s in sections:
        assert len(s.texte) <= 90, f"section {s.indice} dépasse taille_max malgré le repli"


# --- brique 19 (23/09) : regrouper les sections voisines, moins d'appels, la même garantie ---------------


def test_regrouper_zero_ne_change_rien():
    from app.pipeline.decoupage import Section, regrouper

    sections = [Section(0, "a", "x" * 10), Section(1, "b", "y" * 10)]
    assert regrouper(sections, 0) == sections


def test_regrouper_fusionne_les_voisines_sans_perdre_un_caractere():
    from app.pipeline.decoupage import Section, regrouper

    sections = [Section(i, f"Art {i}", f"Texte {i} " * 20) for i in range(5)]     # ~180 caractères chacune
    groupes = regrouper(sections, 400)
    assert [g.indice for g in groupes] == list(range(len(groupes)))
    assert 1 < len(groupes) < 5
    assert "".join(g.texte for g in groupes) == "".join(s.texte for s in sections)  # rien n'est perdu
    assert all(len(g.texte) <= 400 for g in groupes)
    assert groupes[0].titre == "Art 0 / Art 1"


def test_une_section_plus_grande_que_le_budget_reste_seule():
    from app.pipeline.decoupage import Section, regrouper

    grosse = Section(0, "grosse", "z" * 1000)
    petites = [Section(1, "p1", "a" * 50), Section(2, "p2", "b" * 50)]
    groupes = regrouper([grosse, *petites], 300)
    assert groupes[0].texte == "z" * 1000 and len(groupes) == 2


def test_le_v2_regroupe_les_sections_de_c01_en_moins_d_appels(contrat):
    """c01 : 18 articles courts (215 à 980 caractères, mesuré le 21/09) → 18 appels ; regroupés, ~3."""
    from app.llm_client import Bundle
    from app.pipeline.decoupage import decouper, regrouper

    p = Bundle.charger("v2").parametres
    sections = decouper(contrat("c01"), taille_max=int(p["contexte_max_caracteres"]))
    groupes = regrouper(sections, int(p["regroupement_caracteres"]))
    assert len(sections) >= 15 and 1 < len(groupes) <= 5
