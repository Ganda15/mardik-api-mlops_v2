"""Démonstration live du Chantier 2 : un fichier de seuils de démo, chargé par configuration (MARDIK_SEUILS).

Conception Ch2 §4.2 : en démonstration, requetes_min et jours_min sont abaissés « par configuration, jamais par le code ».
Garde-fou : le fichier de démo ne peut changer QUE les temps d'attente et le seuil de capture — jamais un seuil de qualité
(gate, alerte, promotion) : sinon la démo prouverait un autre système que celui livré.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from ops.ajuster_seuils import comparer
from ops.seuils import charger_seuils

RACINE = Path(__file__).resolve().parent.parent
AUTORISES = {"fenetre.requetes_min", "promotion.requetes_min", "promotion.jours_min", "capture.score_global_max"}


def test_le_fichier_de_demo_se_charge():
    demo = charger_seuils(RACINE / "eval" / "thresholds.demo.yml")
    assert demo["fenetre"]["requetes_min"] <= 10 and demo["promotion"]["jours_min"] == 0


def test_la_demo_ne_touche_que_les_temps_d_attente_et_la_capture():
    changes = {c["cle"] for c in comparer(charger_seuils(), charger_seuils(RACINE / "eval" / "thresholds.demo.yml"))}
    assert changes <= AUTORISES, changes - AUTORISES


def test_l_overlay_docker_de_demo_pointe_vers_ce_fichier_pour_l_app_et_le_watcher():
    overlay = yaml.safe_load((RACINE / "docker-compose.demo.yml").read_text(encoding="utf-8"))
    for service in ("app", "watcher", "public"):   # public aussi : capture et seuils cohérents sur le lien de démo
        assert overlay["services"][service]["environment"]["MARDIK_SEUILS"] == "/app/eval/thresholds.demo.yml"
