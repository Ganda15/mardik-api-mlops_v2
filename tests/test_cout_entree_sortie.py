"""Brique 23 (23/09) — le coût sépare les jetons d'entrée et de sortie, aux tarifs du modèle.

Constat : `cout_par_1k_tokens: 0.002` (hérité de la v1) confondait entrée et sortie. Tarifs catalogue lus le
23/09 (liste publique OpenRouter = catalogue OpenAI) : gpt-5.4 entrée 0,0025 $/1k, sortie 0,0150 $/1k — la
sortie coûte 6× l'entrée. Mesuré sur c12 : 26 263 jetons d'entrée, 1 460 de sortie → 0,088 $ au vrai tarif
contre 0,055 avec l'ancien modèle. Le coût rapporté était sous-estimé d'un facteur 1,6 à 2,3.
"""
from __future__ import annotations

import json
import threading
import time

from app.api_v2 import analyser_v2
from app.llm_client import Bundle, LLMClient, ReponseLLM
from app.telemetry import Mesure, MetricsStore


def _bundle(**champs) -> Bundle:
    base = dict(version="v2.0.0", modele="m", prompt="s", parametres={}, schema_sortie=None,
                strategie="map_reduce_clauses")
    return Bundle(**{**base, **champs})


def test_le_cout_separe_entree_et_sortie_quand_les_deux_tarifs_existent():
    client = LLMClient(_bundle(cout_par_1k_entree=0.0025, cout_par_1k_sortie=0.015), mock="on")
    r = ReponseLLM(texte="", latence_ms=1, tokens_entree=1000, tokens_sortie=100)
    assert client.cout_eur(r) == 0.004                       # 1000×0,0025 + 100×0,015, /1000


def test_sans_tarifs_separes_l_ancien_tarif_unique_reste_valable():
    """La v1 (fichier fourni, intouchable) ne connaît que cout_par_1k_tokens : rien ne change pour elle."""
    client = LLMClient(_bundle(cout_par_1k_tokens=0.002), mock="on")
    r = ReponseLLM(texte="", latence_ms=1, tokens_entree=1000, tokens_sortie=100)
    assert client.cout_eur(r) == 0.0022


def test_le_bundle_v2_porte_les_deux_tarifs_et_la_sortie_coute_plus():
    b = Bundle.charger("v2")
    assert b.cout_par_1k_entree > 0 and b.cout_par_1k_sortie > b.cout_par_1k_entree
    assert b.cout_par_1k_tokens == 0.0                       # plus de tarif unique trompeur sur la v2


def test_une_mesure_garde_le_partage_et_une_ancienne_ligne_se_relit(tmp_path):
    store = MetricsStore(tmp_path / "m.jsonl")
    store.enregistrer(Mesure(ts=time.time(), version="v2.0.0", route="/v2/analyse", latence_ms=1,
                             tokens=1100, tokens_entree=1000, tokens_sortie=100, cout_eur=0.004))
    ancienne = {"ts": time.time(), "version": "v2.0.0", "route": "/v2/analyse", "latence_ms": 1, "tokens": 50}
    (tmp_path / "m.jsonl").open("a", encoding="utf-8").write(json.dumps(ancienne) + "\n")
    m1, m2 = store.lire()
    assert (m1.tokens_entree, m1.tokens_sortie) == (1000, 100)
    assert (m2.tokens_entree, m2.tokens_sortie) == (0, 0)    # ligne d'avant la brique 23 : lisible, à zéro


class _ClientFixe:
    """Un faux fournisseur : chaque appel de section coûte 50 jetons d'entrée et 30 de sortie."""

    def __init__(self) -> None:
        self.bundle = Bundle.charger("v2")
        self.bundle.parametres["regroupement_caracteres"] = 0
        self._verrou = threading.Lock()
        self.appels = 0

    def completer(self, prompt_utilisateur: str, *, json_mode: bool = False) -> ReponseLLM:
        with self._verrou:
            self.appels += 1
        return ReponseLLM(texte=json.dumps({"clauses": []}), latence_ms=1, tokens_entree=50, tokens_sortie=30, mock=True)

    def cout_eur(self, reponse: ReponseLLM) -> float:
        return LLMClient.cout_eur(self, reponse)  # type: ignore[arg-type]  — la vraie formule, sur ce bundle


def test_l_analyse_v2_journalise_le_partage_des_jetons(telemetry, metriques):
    client = _ClientFixe()
    texte = "\n".join(f"Article {i} — Titre {i}\n\nTexte de la section {i}.\n" for i in range(1, 5))
    analyser_v2(texte, client, telemetry)
    m = telemetry.metriques.lire()[-1]
    assert client.appels == 4
    assert (m.tokens_entree, m.tokens_sortie, m.tokens) == (200, 120, 320)
    b = client.bundle
    assert m.cout_eur == round((200 * b.cout_par_1k_entree + 120 * b.cout_par_1k_sortie) / 1000, 6)
