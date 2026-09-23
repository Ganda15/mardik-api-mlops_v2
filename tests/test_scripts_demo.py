"""La démo Chantier 2 en une commande, sans make (absent sur le poste d'Era : PowerShell 5.1, Git Bash).

Trouvé le 23/09 : relancer le profil « public » avec `docker compose` seul recrée app/watcher/public SANS
l'overlay de démo (seuils réels, watcher 60 s). Le lanceur passe TOUJOURS les deux fichiers.
"""
from __future__ import annotations

import pytest

from scripts import demo


def test_chaque_action_passe_les_deux_fichiers_compose():
    for action in ("up", "public", "down"):
        cmd = demo.commande(action)
        assert cmd[:2] == ["docker", "compose"]
        assert cmd[cmd.index("-f") + 1] == "docker-compose.yml"
        assert "docker-compose.demo.yml" in cmd


def test_public_et_down_portent_le_profil_public_up_non():
    assert "--profile" in demo.commande("public") and "--profile" in demo.commande("down")
    assert "--profile" not in demo.commande("up")
    assert demo.commande("down")[-1] == "down"


def test_action_inconnue_refusee():
    with pytest.raises(ValueError):
        demo.commande("restart")


def test_main_lance_la_commande_sans_docker_ici(monkeypatch, capsys):
    appels = []

    class _R:
        returncode = 0

    monkeypatch.setattr(demo.subprocess, "run", lambda cmd, **kw: appels.append(cmd) or _R())
    monkeypatch.setattr(demo, "lien_tunnel", lambda: "https://exemple.trycloudflare.com")
    assert demo.main(["public"]) == 0
    assert appels == [demo.commande("public")]
    assert "https://exemple.trycloudflare.com" in capsys.readouterr().out


def test_le_lien_du_tunnel_est_lu_depuis_le_dernier_demarrage_du_conteneur(monkeypatch):
    """23/09 : un conteneur tunnel redemarre garde ses anciens journaux — le lanceur affichait l'adresse
    de la veille, morte. Le lien doit venir des journaux POSTERIEURS au demarrage du conteneur."""
    appels = []

    class _R:
        def __init__(self, out):
            self.stdout = out
            self.returncode = 0

    def _run(cmd, **kw):
        appels.append(cmd)
        if "inspect" in cmd:
            return _R("2026-09-23T17:40:00.000000000Z\n")
        return _R("INF https://nouveau-lien.trycloudflare.com\n")

    monkeypatch.setattr(demo.subprocess, "run", _run)
    assert demo.lien_tunnel() == "https://nouveau-lien.trycloudflare.com"
    logs = next(c for c in appels if "logs" in c)
    assert "--since" in logs and "2026-09-23T17:40:00" in logs[logs.index("--since") + 1]
