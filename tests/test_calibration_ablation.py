"""Ablation : retirer un article entier d'un contrat de référence donne une étiquette connue par construction —
la clause n'y est plus. Si le modèle la signale encore, c'est une erreur réelle, mesurable, là où il hésite."""
from eval.calibration import TITRE_VERS_TYPE, evaluer_loco, retirer_article, variantes_ablation

TEXTE = """CONTRAT

Article 1 — Objet

Le présent contrat a pour objet X.

Article 2 — Garantie

Le Prestataire garantit les livrables six mois.

Article 3 — Résiliation

Chaque partie peut résilier avec un préavis de trois mois.
"""


def test_retirer_article_supprime_titre_et_corps_seulement():
    t = retirer_article(TEXTE, "Garantie")
    assert "Garantie" not in t and "garantit" not in t
    assert "Article 1 — Objet" in t and "Article 3 — Résiliation" in t and "préavis de trois mois" in t


def test_retirer_le_dernier_article():
    t = retirer_article(TEXTE, "Résiliation")
    assert "Résiliation" not in t and "préavis" not in t and "Garantie" in t


def test_retirer_un_article_absent_rend_none():
    assert retirer_article(TEXTE, "Force majeure") is None


def test_les_titres_distinctifs_seulement():
    # durée, prix et droit applicable sont cités ailleurs dans les contrats : étiquette non fiable, jamais retirés
    assert "Durée" not in TITRE_VERS_TYPE and "Prix et modalités de paiement" not in TITRE_VERS_TYPE
    assert TITRE_VERS_TYPE["Garantie"] == "garantie" and TITRE_VERS_TYPE["Reconduction"] == "reconduction tacite"


def test_variantes_etiquette_sans_le_type_retire():
    attendues = {"garantie", "résiliation", "durée"}
    vs = variantes_ablation("cX", TEXTE, attendues, max_par_contrat=3)
    assert {v["retire"] for v in vs} == {"garantie", "résiliation"}
    for v in vs:
        assert v["retire"] not in v["attendues"]
        assert v["attendues"] == attendues - {v["retire"]}
        assert v["contrat"] == "cX"


def test_variantes_respectent_le_plafond():
    vs = variantes_ablation("cX", TEXTE, {"garantie", "résiliation"}, max_par_contrat=1)
    assert len(vs) == 1


def test_variante_ignoree_si_le_type_nest_pas_attendu():
    vs = variantes_ablation("cX", TEXTE, {"résiliation"}, max_par_contrat=3)
    assert {v["retire"] for v in vs} == {"résiliation"}


def test_loco_groupe_les_variantes_avec_leur_contrat_source():
    # une variante de c1 ne doit jamais servir à calibrer c1 : même "contrat" -> même groupe
    points = ([{"contrat": "c1", "score": 0.9, "correct": 1}] * 5 + [{"contrat": "c1", "score": 0.8, "correct": 0}] * 2
              + [{"contrat": "c2", "score": 0.9, "correct": 1}] * 5 + [{"contrat": "c2", "score": 0.8, "correct": 0}] * 2)
    r = evaluer_loco(points)
    assert r["contrats"] == 2 and r["n"] == 14
