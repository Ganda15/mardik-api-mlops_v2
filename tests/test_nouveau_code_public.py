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


def test_le_jeton_d_administration_a_son_propre_fichier(tmp_path):
    """Brique 16 : le jeton qui autorise le rollback est distinct de la clé du lien public."""
    from scripts.nouveau_code_public import ecrire_jeton_admin

    chemin = tmp_path / "admin.env"
    jeton = ecrire_jeton_admin(chemin)
    assert chemin.read_text(encoding="utf-8") == f"MARDIK_ADMIN_TOKEN={jeton}\n"
    assert len(jeton) >= 20


def test_admin_env_est_ignore_par_git():
    from pathlib import Path

    ignores = (Path(__file__).resolve().parent.parent / ".gitignore").read_text(encoding="utf-8")
    assert "admin.env" in ignores.splitlines()


def test_le_script_n_affiche_jamais_le_secret_en_entier(tmp_path, monkeypatch, capsys):
    """23/09 : trois secrets affichés par ce script ont fini collés dans un chat — copier la sortie du
    terminal est le geste normal. Le script n'affiche donc que les 4 premiers caractères."""
    import scripts.nouveau_code_public as s

    monkeypatch.setattr(s, "CHEMIN_DEFAUT", tmp_path / "public.env")
    monkeypatch.setattr(s, "CHEMIN_ADMIN", tmp_path / "admin.env")
    for argv in (["prog"], ["prog", "--admin"]):
        monkeypatch.setattr("sys.argv", argv)
        s.main()
    sortie = capsys.readouterr().out
    code = (tmp_path / "public.env").read_text(encoding="utf-8").split("\n")[0].split("=", 1)[1]
    jeton = (tmp_path / "admin.env").read_text(encoding="utf-8").strip().split("=", 1)[1]
    assert code not in sortie and jeton not in sortie
    assert code[:4] in sortie and jeton[:4] in sortie
