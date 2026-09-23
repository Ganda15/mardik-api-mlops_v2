"""Chargement des seuils — un seul fichier versionné, ``eval/thresholds.yml``. Brique 13 (Chantier 2).

    charger_seuils(chemin=None) -> dict

Échec fermé : fichier absent, illisible ou incomplet → ``ErreurSeuils``, jamais un seuil deviné.
``MARDIK_SEUILS`` pointe vers un autre fichier (démonstration : ``requetes_min`` abaissé « par
configuration, jamais par le code », conception Ch2 §4.2).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

CHEMIN_SEUILS = Path(__file__).resolve().parent.parent / "eval" / "thresholds.yml"
SECTIONS = ("gate", "fenetre", "rollback_alerte", "promotion", "capture", "signature")


class ErreurSeuils(RuntimeError):
    """Les seuils ne peuvent pas être lus : aucune décision ne doit en sortir."""


def charger_seuils(chemin: Path | str | None = None) -> dict[str, Any]:
    source = Path(chemin or os.environ.get("MARDIK_SEUILS") or CHEMIN_SEUILS)
    if not source.is_file():
        raise ErreurSeuils(f"fichier de seuils introuvable : {source}")
    try:
        seuils = yaml.safe_load(source.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ErreurSeuils(f"fichier de seuils illisible : {source} ({exc})") from exc
    if not isinstance(seuils, dict):
        raise ErreurSeuils(f"fichier de seuils vide ou mal formé : {source}")
    manquantes = [s for s in SECTIONS if not isinstance(seuils.get(s), dict)]
    if manquantes:
        raise ErreurSeuils(f"section(s) manquante(s) dans {source.name} : {', '.join(manquantes)}")
    return seuils
