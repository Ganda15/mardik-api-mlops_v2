"""Extraction des clauses d'une section (un appel LLM, sortie JSON contrainte). Brique 3.

    extraire(section: Section, client: LLMClient) -> tuple[list[Clause], ReponseLLM]

Un appel ``client.completer(..., json_mode=True)`` par section : le prompt système vient
du bundle (``client.bundle.prompt``, injecté automatiquement par ``completer()`` — pas
reconstruit ici), le prompt utilisateur porte le titre et le texte de la section.

La réponse est parsée selon ``schema_sortie`` ; toute clause qui ne respecte pas le schéma
(JSON invalide, champ manquant, type hors vocabulaire, confiance hors [0, 1]) est ignorée
et signalée par un journal structuré — jamais un plantage de toute l'analyse pour une seule
clause mal formée. ``sections=[section.indice]`` et ``confiance_llm`` sont posés ici ; le
score composite (``confiance``) est calculé plus tard, par ``confiance.py::scorer``.
"""
from __future__ import annotations

import structlog

from app.llm_client import TYPES_CLAUSES, ErreurLLM, LLMClient, ReponseLLM
from app.pipeline.confiance import Clause
from app.pipeline.decoupage import Section

_logger = structlog.get_logger(__name__)


def extraire(section: Section, client: LLMClient) -> tuple[list[Clause], ReponseLLM]:
    prompt_utilisateur = f"Titre : {section.titre}\n\n{section.texte}"
    reponse = client.completer(prompt_utilisateur, json_mode=True)

    try:
        data = reponse.json()
    except ErreurLLM as exc:
        _logger.warning("extraction.reponse_non_json", section=section.indice, cause=str(exc))
        return [], reponse

    items = data.get("clauses") if isinstance(data, dict) else None
    if not isinstance(items, list):
        _logger.warning(
            "extraction.schema_invalide", section=section.indice, motif="clauses absent ou pas une liste"
        )
        return [], reponse

    clauses: list[Clause] = []
    for item in items:
        erreur = _valider_clause(item)
        if erreur:
            _logger.warning("extraction.clause_ignoree", section=section.indice, motif=erreur, item=item)
            continue
        clauses.append(
            Clause(
                type=item["type"],
                extrait=str(item["extrait"]),
                confiance_llm=float(item["confiance"]),
                sections=[section.indice],
            )
        )
    return clauses, reponse


def _valider_clause(item: object) -> str | None:
    """Renvoie la raison si ``item`` ne respecte pas le schéma, ``None`` s'il est valide."""
    if not isinstance(item, dict):
        return "pas un objet JSON"
    for champ in ("type", "extrait", "confiance"):
        if champ not in item:
            return f"champ manquant : {champ}"
    if item["type"] not in TYPES_CLAUSES:
        return f"type hors vocabulaire : {item['type']!r}"
    try:
        confiance = float(item["confiance"])
    except (TypeError, ValueError):
        return "confiance non numérique"
    if not (0.0 <= confiance <= 1.0):
        return f"confiance hors [0, 1] : {confiance}"
    return None
