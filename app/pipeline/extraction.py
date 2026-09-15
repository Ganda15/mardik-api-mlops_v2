"""Extraction des clauses d'une section (un appel LLM, sortie JSON contrainte). [STUB]

Contrat attendu :

    extraire(section: Section, client: LLMClient) -> tuple[list[Clause], ReponseLLM]

* Un appel ``client.completer(..., json_mode=True)`` par section : le prompt
  système vient du bundle v2, le prompt utilisateur contient le titre et le
  texte de la section.
* La réponse est parsée selon ``bundle.schema_sortie`` ; une réponse qui ne
  respecte pas le schéma (JSON invalide, champ manquant, type inconnu,
  confiance hors [0, 1]) ne doit pas faire planter l'analyse : la clause
  fautive est ignorée et l'incident est signalé (log / span).
* Chaque ``Clause`` renvoyée porte ``sections=[section.indice]`` et
  ``confiance_llm`` = la valeur déclarée par le modèle ; le score composite
  est calculé plus tard (``confiance.py``).
* La ``ReponseLLM`` est renvoyée telle quelle pour que l'appelant puisse
  agréger latence, tokens et coût.

Indices : ``app.llm_client.TYPES_CLAUSES`` liste les types valides ;
``ReponseLLM.json()`` extrait le JSON d'une réponse (et lève ``ErreurLLM`` sinon).
"""
from __future__ import annotations

from app.llm_client import LLMClient, ReponseLLM
from app.pipeline.confiance import Clause
from app.pipeline.decoupage import Section


def extraire(section: Section, client: LLMClient) -> tuple[list[Clause], ReponseLLM]:
    raise NotImplementedError("pipeline.extraction.extraire — un appel LLM par section, JSON contraint")
