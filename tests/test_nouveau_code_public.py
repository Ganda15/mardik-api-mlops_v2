"""F3 — le fichier de code du lien public est créé par un script, jamais tapé à la main.

Le 23/09, trois codes ont fui dans un chat et un quatrième a été lancé avec le texte
littéral « LE_CODE » : remplacer un gabarit à la main ne marche pas. Le script écrit
``public.env`` (ignoré par git) et affiche le code une seule fois.
"""
from __future__ import annotations

import re

from scripts.nouveau_code_public import ecrire_fichier_code


def test_ecrit_une_cle_et_un_plafond(tmp_path):
    chemin = tmp_path / "public.env"
    code = ecrire_fichier_code(chemin, budget_eur=2.0)
    contenu = chemin.read_text(encoding="utf-8")
    assert f"MARDIK_API_KEY={code}\n" in contenu
    assert "MARDIK_BUDGET_JOUR_EUR=2.0\n" in contenu
    assert re.fullmatch(r"[A-Za-z0-9_\-]{16}", code)


def test_chaque_appel_donne_un_nouveau_code(tmp_path):
    a = ecrire_fichier_code(tmp_path / "a.env")
    b = ecrire_fichier_code(tmp_path / "b.env")
    assert a != b


def test_public_env_est_ignore_par_git():
    from pathlib import Path

    ignores = (Path(__file__).resolve().parent.parent / ".gitignore").read_text(encoding="utf-8")
    assert "public.env" in ignores.splitlines()
