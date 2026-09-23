"""Score de confiance composite, par clause puis global. Brique 5.

    scorer(clauses: list[Clause], texte: str) -> tuple[list[Clause], float]

Le score combine deux signaux indépendants : ce que le modèle déclare (``confiance_llm``) et
une vérification faite SANS lui — l'extrait cité figure-t-il vraiment, mot pour mot, dans le
contrat ? Un extrait absent du texte (citation inventée) ramène le score composite à 0, quelle
que soit la confiance déclarée : c'est la garantie explicite de cette brique — un modèle sûr de
lui sur une citation inventée obtient un score bas, jamais un chiffre rassurant. Une clause vue
dans plusieurs sections reçoit un petit bonus (corroboration faible, pas une preuve), plafonné
à 1.0. Le score global est la moyenne des scores par clause, 0 si la liste est vide.
"""
from __future__ import annotations

from dataclasses import dataclass, field

BONUS_MULTI_SECTIONS = 0.05  # valeur de travail, à ajuster avec le golden dataset (brique 7)


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
    for clause in clauses:
        if _extrait_verifie(clause.extrait, texte):
            bonus = BONUS_MULTI_SECTIONS if len(clause.sections) > 1 else 0.0
            clause.confiance = min(1.0, clause.confiance_llm + bonus)
        else:
            clause.confiance = 0.0  # citation invérifiable : jamais un chiffre rassurant

    score_global = sum(c.confiance for c in clauses) / len(clauses) if clauses else 0.0
    return clauses, score_global


def clauses_prouvees(clauses: list[Clause], texte: str) -> list[Clause]:
    """Clauses dont l'extrait figure mot pour mot dans le texte — les seules renvoyées.

    Décision du 23/09 (red-team Era, run e04cea659151) : sur un texte qui n'est pas un
    contrat, le modèle peut annoncer les quatorze types avec des extraits vides ou
    inventés ; le score les ramenait à 0 mais la réponse les listait quand même — et le
    gate comptait chaque type renvoyé comme détecté. Une clause sans extrait vérifié
    n'est pas une détection, c'est du bruit : elle n'a pas sa place dans la réponse.
    """
    return [c for c in clauses if _extrait_verifie(c.extrait, texte)]


def _extrait_verifie(extrait: str, texte: str) -> bool:
    """Vrai seulement si ``extrait``, non vide, figure mot pour mot dans ``texte``.

    Le garde ``extrait.strip()`` existe précisément parce qu'en Python ``"" in texte``
    vaut toujours ``True`` — sans lui, un extrait vide serait à tort considéré comme
    « vérifié ».
    """
    extrait = extrait.strip()
    return bool(extrait) and extrait in texte


# Conception Ch1, H6 : les bornes du « niveau de certitude ». Elles vivent dans le bundle
# (``parametres.seuils_libelle``, configuration versionnée) ; ce défaut ne sert qu'aux
# bundles publiés avant l'ajout du champ (v2.0.0 dans le registre).
SEUILS_LIBELLE_DEFAUT = {"haute": 0.8, "moyenne": 0.5}


def libeller(score: float, seuils: dict | None = None) -> str:
    """Le niveau de certitude pour le juriste : ``haute`` >= borne haute, ``moyenne`` >= borne
    moyenne, sinon ``basse``. Une règle de décision, pas une couleur : haute → valider,
    moyenne → vérifier les clauses sous 0,7, basse → relire entièrement (H6)."""
    bornes = seuils or SEUILS_LIBELLE_DEFAUT
    if score >= bornes["haute"]:
        return "haute"
    if score >= bornes["moyenne"]:
        return "moyenne"
    return "basse"
