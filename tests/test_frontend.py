"""Brique F2 — le frontend : une page unique servie par l'API (conception Ch1, H15).

H15 : page unique, sans authentification en démonstration, affichant les clauses, le
niveau de certitude et la version qui a répondu. Servie par la même application FastAPI :
pas de framework, pas d'étape de build, pas d'appel cross-origin.

Ces tests figent ce qui ne se voit pas à l'œil : la page ne construit jamais de HTML à
partir des données (les extraits viennent du contrat et du modèle — c'est la faille XSS
déjà corrigée une fois dans le tableau de bord, commit 09172bd), et elle ne charge rien
depuis Internet (elle doit marcher hors ligne, sans CDN ni pisteur).
"""
from __future__ import annotations

import re

import pytest


@pytest.fixture
def page(client) -> str:
    r = client.get("/")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/html")
    return r.text


def test_la_racine_sert_la_page(page):
    assert 'lang="fr"' in page
    assert "<textarea" in page and "<button" in page


def test_la_page_appelle_la_gateway_et_peut_forcer_v2(page):
    """Par défaut le chemin de production (la gateway, qui route v1/v2) ; v2 direct pour la démo."""
    assert '"/analyse"' in page
    assert '"/v2/analyse"' in page


def test_la_page_affiche_la_regle_de_decision_pas_seulement_une_couleur(page):
    """H6 : haute → valider, moyenne → vérifier, basse → relire."""
    for mot in ("valider", "Vérifiez", "Relisez"):
        assert mot in page


def test_la_page_ne_construit_jamais_de_html_depuis_les_donnees(page):
    for interdit in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write"):
        assert interdit not in page, interdit


def test_la_page_ne_charge_rien_depuis_internet(page):
    assert re.search(r'(src|href)\s*=\s*"https?://', page) is None


def test_la_page_envoie_la_cle_et_explique_les_refus(page):
    """F3 : sur le lien public, la page porte la clé et traduit 401 / 429 pour le juriste."""
    assert 'id="cle"' in page and 'type="password"' in page
    assert "X-API-Key" in page
    assert "r.status === 401" in page and "r.status === 429" in page
