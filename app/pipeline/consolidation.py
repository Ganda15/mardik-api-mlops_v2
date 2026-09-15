"""Fusion et dédoublonnage des clauses extraites section par section (*reduce*). [STUB]

Contrat attendu :

    consolider(par_section: list[list[Clause]]) -> list[Clause]

* Deux clauses du même ``type`` trouvées dans des sections différentes sont
  **une seule** clause dans le résultat : on garde l'extrait le plus long (le
  plus informatif), on fusionne les ``sections`` et on retient la
  ``confiance_llm`` maximale déclarée.
* L'ordre de sortie suit l'ordre d'apparition dans le contrat (première
  section où la clause a été vue).
* Le résultat ne contient jamais deux clauses de même type.
"""
from __future__ import annotations

from app.pipeline.confiance import Clause


def consolider(par_section: list[list[Clause]]) -> list[Clause]:
    raise NotImplementedError("pipeline.consolidation.consolider — fusion + dédoublonnage")
