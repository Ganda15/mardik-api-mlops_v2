"""Calibration du score de confiance — ce que « 0,8 » veut dire, mesuré.

    calibrer(score, parametres) -> float | None

Le score brut d'une clause (confiance déclarée par le modèle, mise à 0 si la citation est invérifiable) n'est pas une
probabilité : un modèle peut se dire sûr à 0,99 et se tromper une fois sur vingt. La calibration de Platt apprend,
sur le jeu de référence étiqueté, une courbe logistique  p = σ(a · logit(score) + b)  qui transforme le score brut en
probabilité mesurée que la clause renvoyée soit juste. Les paramètres vivent dans le bundle (parametres.calibration) :
ils sont versionnés, entrent dans l'empreinte de la version et voyagent dans le manifeste.

Le score brut n'est PAS remplacé : la dérive, les seuils d'alerte et la signature du watcher sont mesurés sur lui.
Sans paramètres de calibration, la fonction rend None — jamais un chiffre inventé.
"""
from __future__ import annotations

import math

EPS = 1e-4


def calibrer(score: float, parametres: dict | None) -> float | None:
    if not parametres or parametres.get("methode") != "platt":
        return None
    s = min(max(float(score), EPS), 1 - EPS)
    z = parametres["a"] * math.log(s / (1 - s)) + parametres["b"]
    z = max(min(z, 50.0), -50.0)
    p = 1.0 / (1.0 + math.exp(-z))
    # Plafond statistique : n clauses justes sur n ne prouvent pas « jamais faux » (règle de trois : erreur < 3/n).
    return round(min(p, parametres.get("plafond", 1.0)), 4)
