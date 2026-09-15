"""Score de confiance composite, par clause puis global. [STUB]

Contrat attendu :

    scorer(clauses: list[Clause], texte: str) -> tuple[list[Clause], float]

* Une ``Clause`` porte ``type``, ``extrait``, ``confiance_llm`` (la certitude
  déclarée par le modèle, 0–1), ``sections`` (indices des sections où elle a
  été vue) et ``confiance`` (le score composite, à calculer ici).
* Le score composite combine au moins deux signaux indépendants : ce que le
  modèle déclare, et une vérification que l'on peut faire *sans* lui (par
  exemple : l'extrait cité figure-t-il vraiment dans le contrat ? la clause
  a-t-elle été vue dans plusieurs sections ?). Un modèle très sûr de lui sur
  une citation inventée doit obtenir un score bas.
* Le score global est un résumé des scores par clause (0 si aucune clause) ;
  c'est lui que le client lit « pour savoir quand relire ».
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Clause:
    type: str
    extrait: str
    confiance_llm: float
    sections: list[int] = field(default_factory=list)
    confiance: float = 0.0

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "extrait": self.extrait,
            "confiance": round(self.confiance, 3),
            "sections": self.sections,
        }


def scorer(clauses: list[Clause], texte: str) -> tuple[list[Clause], float]:
    raise NotImplementedError("pipeline.confiance.scorer — score composite par clause + global")
