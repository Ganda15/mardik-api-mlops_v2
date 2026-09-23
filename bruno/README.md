# Collection Bruno — Mardik, la nouvelle version (brique 22, 23/09)

Idée de David en réunion : chaque requête de la démo prête à envoyer, avec son explication à côté.
Ouvrir Bruno → *Open collection* → ce dossier. Environnement `local` : `baseUrl` = l'API sur ce poste,
`publicUrl` = le lien du tunnel (change à chaque démarrage : `uv run python -m scripts.demo public`).

**Secrets** (onglet *Secrets* de l'environnement, jamais dans un fichier du dépôt) :
`apiKey` = le code de `public.env`, `adminToken` = le jeton de `admin.env` (`notepad admin.env`).

Ordre = ordre de la démo : v1 intact → v2 → erreur explicite → gateway et version servie → pilotage →
rollback (agit sur la production !) → lien public verrouillé. Chaque requête a un onglet *Docs* qui dit
ce qu'elle prouve. Bruno n'est pas installé sur le runner : `tests/test_bruno.py` fige la forme des fichiers.
