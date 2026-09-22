"""Fusion et dédoublonnage des clauses extraites section par section (*reduce*). Brique 4.

    consolider(par_section: list[list[Clause]]) -> list[Clause]

Deux clauses du même ``type`` trouvées dans des sections différentes deviennent **une seule**
clause dans le résultat : l'extrait le plus long (le plus informatif) est conservé, les
``sections`` sont fusionnées (union triée, jamais de doublon d'indice), et la ``confiance_llm``
retenue est la plus haute déclarée. L'ordre de sortie suit l'ordre d'apparition dans le contrat
— la première section où le type a été vu. Le résultat ne contient jamais deux clauses du même
type : garanti par construction (un seul emplacement par type dans le dictionnaire de fusion).
"""
from __future__ import annotations

from app.pipeline.confiance import Clause


def consolider(par_section: list[list[Clause]]) -> list[Clause]:
    fusionnees: dict[str, Clause] = {}
    ordre: list[str] = []

    for clauses in par_section:
        for clause in clauses:
            if clause.type not in fusionnees:
                fusionnees[clause.type] = Clause(
                    type=clause.type,
                    extrait=clause.extrait,
                    confiance_llm=clause.confiance_llm,
                    sections=list(clause.sections),
                )
                ordre.append(clause.type)
                continue

            existante = fusionnees[clause.type]
            if len(clause.extrait) > len(existante.extrait):
                existante.extrait = clause.extrait
            existante.confiance_llm = max(existante.confiance_llm, clause.confiance_llm)
            existante.sections = sorted(set(existante.sections) | set(clause.sections))

    return [fusionnees[type_] for type_ in ordre]
