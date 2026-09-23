"""Brique F3 — protéger l'instance exposée par un tunnel (option C, décision d'Era du 23/09).

Un lien public vers une route qui appelle Azure, c'est un budget que n'importe qui peut
dépenser. Deux protections, actives SEULEMENT sur l'instance lancée avec les variables :

* ``MARDIK_API_KEY`` : chaque POST (les trois routes qui appellent le modèle) exige l'en-tête
  ``X-API-Key`` (conception Ch1 §2.3) ; les GET restent ouverts pour que la page se charge ;
* ``MARDIK_BUDGET_JOUR_EUR`` : au-delà de ce coût sur 24 h glissantes (lu dans les ``Mesure``),
  les POST sont refusés en ``429``.

Sans ces variables, rien ne change : l'instance locale et le client v1 fonctionnent comme avant.
Un refus est décidé AVANT tout appel au modèle : il ne coûte rien.
"""
from __future__ import annotations

import time

import pytest

from app.telemetry import Mesure

CLE = "cle-de-test-123"
ROUTES_PAYANTES = ("/v1/analyse", "/v2/analyse", "/analyse")


def test_sans_variable_rien_ne_change(client, contrat):
    for route in ROUTES_PAYANTES:
        assert client.post(route, json={"texte": contrat("c01")}).status_code == 200, route


@pytest.mark.parametrize("route", ROUTES_PAYANTES)
def test_cle_exigee_sur_chaque_route_payante(client, contrat, monkeypatch, route):
    monkeypatch.setenv("MARDIK_API_KEY", CLE)
    r = client.post(route, json={"texte": contrat("c01")})
    assert r.status_code == 401, r.text
    assert "X-API-Key" in r.json()["detail"]


def test_mauvaise_cle_refusee(client, contrat, monkeypatch):
    monkeypatch.setenv("MARDIK_API_KEY", CLE)
    r = client.post("/v2/analyse", json={"texte": contrat("c01")}, headers={"X-API-Key": "pas-la-bonne"})
    assert r.status_code == 401


def test_bonne_cle_acceptee(client, contrat, monkeypatch):
    monkeypatch.setenv("MARDIK_API_KEY", CLE)
    r = client.post("/v2/analyse", json={"texte": contrat("c01")}, headers={"X-API-Key": CLE})
    assert r.status_code == 200, r.text


def test_les_get_restent_ouverts(client, monkeypatch):
    """La page doit se charger pour qu'on puisse y saisir la clé."""
    monkeypatch.setenv("MARDIK_API_KEY", CLE)
    for chemin in ("/", "/health", "/gateway/etat"):
        assert client.get(chemin).status_code == 200, chemin


def test_un_refus_ne_coute_rien(client, contrat, monkeypatch, metriques):
    monkeypatch.setenv("MARDIK_API_KEY", CLE)
    client.post("/v2/analyse", json={"texte": contrat("c01")})
    assert metriques.lire() == []  # aucune Mesure : le modèle n'a pas été appelé


def _depense(metriques, cout_eur: float, il_y_a_s: float = 0.0) -> None:
    metriques.enregistrer(
        Mesure(ts=time.time() - il_y_a_s, version="v2.0.0", route="/v2/analyse", latence_ms=1.0, cout_eur=cout_eur)
    )


def test_budget_atteint_renvoie_429(client, contrat, monkeypatch, metriques):
    monkeypatch.setenv("MARDIK_BUDGET_JOUR_EUR", "0.10")
    _depense(metriques, 0.12)
    r = client.post("/v2/analyse", json={"texte": contrat("c01")})
    assert r.status_code == 429, r.text
    detail = r.json()["detail"]
    assert "budget" in detail
    # Vu le 23/09 dans le navigateur : arrondis à 2 décimales, 0,006 et 0,005 s'affichaient tous deux « 0.01 ».
    assert "0,120 €" in detail and "0,100 €" in detail


def test_budget_sous_le_plafond_laisse_passer(client, contrat, monkeypatch, metriques):
    monkeypatch.setenv("MARDIK_BUDGET_JOUR_EUR", "0.10")
    _depense(metriques, 0.05)
    assert client.post("/v2/analyse", json={"texte": contrat("c01")}).status_code == 200


def test_budget_ne_compte_que_les_24_dernieres_heures(client, contrat, monkeypatch, metriques):
    monkeypatch.setenv("MARDIK_BUDGET_JOUR_EUR", "0.10")
    _depense(metriques, 5.0, il_y_a_s=25 * 3600)
    assert client.post("/v2/analyse", json={"texte": contrat("c01")}).status_code == 200


def test_la_cle_passe_avant_le_budget(client, contrat, monkeypatch, metriques):
    """Sans clé, on ne dit pas où en est le budget : 401, pas 429."""
    monkeypatch.setenv("MARDIK_API_KEY", CLE)
    monkeypatch.setenv("MARDIK_BUDGET_JOUR_EUR", "0.10")
    _depense(metriques, 0.12)
    assert client.post("/v2/analyse", json={"texte": contrat("c01")}).status_code == 401


# --- l'instance publique échoue fermée : sans clé, elle ne démarre pas --------------------


def test_instance_publique_refuse_de_demarrer_sans_cle(monkeypatch):
    """Docker lance le service public avec MARDIK_EXIGER_CLE=1 : un fichier de code vide ou
    oublié ne doit jamais publier un lien ouvert sur le budget Azure."""
    from app.main import create_app

    monkeypatch.setenv("MARDIK_EXIGER_CLE", "1")
    monkeypatch.delenv("MARDIK_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="MARDIK_API_KEY"):
        create_app()


def test_instance_publique_demarre_avec_une_cle(monkeypatch):
    from app.main import create_app

    monkeypatch.setenv("MARDIK_EXIGER_CLE", "1")
    monkeypatch.setenv("MARDIK_API_KEY", CLE)
    assert create_app() is not None
