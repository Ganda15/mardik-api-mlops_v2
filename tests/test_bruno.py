"""Brique 22 (23/09) — la collection Bruno de la démo : une requête par étape, son explication à côté.

Bruno n'est pas installé sur le runner : on fige la forme des fichiers `.bru` (Bruno Lang), pas leur
exécution — chaque requête a un `meta`, une URL sur une variable d'environnement, un onglet `docs`, et
aucun secret ni adresse réelle en clair.
"""
from __future__ import annotations

import re
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
BRUNO = RACINE / "bruno"


def _requetes() -> list[Path]:
    return sorted(BRUNO.glob("*.bru"))


def test_une_requete_par_etape_de_la_demo_avec_son_explication():
    fichiers = _requetes()
    assert len(fichiers) >= 10
    seqs = []
    for f in fichiers:
        t = f.read_text(encoding="utf-8")
        assert "meta {" in t and "docs {" in t, f.name
        assert re.search(r"url: \{\{(baseUrl|publicUrl)\}\}/", t), f.name     # jamais une adresse en dur
        seqs.append(int(re.search(r"seq: (\d+)", t).group(1)))
    assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs)


def test_aucun_secret_ni_adresse_reelle_dans_la_collection():
    for f in [*_requetes(), BRUNO / "environments" / "local.bru"]:
        t = f.read_text(encoding="utf-8")
        assert "trycloudflare.com" not in t or "REMPLACER" in t, f.name
        assert not re.search(r"X-(Admin-Token|API-Key): (?!\{\{)", t), f.name   # toujours une variable


def test_l_environnement_declare_les_variables_et_les_secrets():
    env = (BRUNO / "environments" / "local.bru").read_text(encoding="utf-8")
    assert "baseUrl:" in env and "publicUrl:" in env
    assert "vars:secret" in env and "apiKey" in env and "adminToken" in env
