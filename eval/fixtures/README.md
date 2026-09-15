# Fixtures — réponses LLM enregistrées (mode `MOCK=on`)

Un fichier JSON par appel enregistré, nommé par l'empreinte SHA-256 (20 car.)
de `modele + prompt système + prompt utilisateur` :

```json
{"modele": "llama3.2:3b", "version": "v2.0.0", "texte": "{\"clauses\": [...]}",
 "latence_ms": 2310.4, "tokens_entree": 1480, "tokens_sortie": 96, "extrait_prompt": "Section : ..."}
```

- `MOCK=on`     : le client rejoue la fixture correspondante, sans réseau.
                  Si aucune fixture ne correspond (prompt différent), une
                  **réponse de repli** déterministe est construite par mots-clés
                  (`app/llm_client.py::reponse_de_repli`) — la CI reste verte,
                  mais ce n'est pas un modèle.
- `MOCK=record` : le client appelle le vrai fournisseur et enregistre ici.
- `make fixtures` : rejoue le gate v1 et v2 en `MOCK=record`.

À faire par le formateur avant J1 : exécuter `make fixtures` une fois sur la
branche solution avec le vrai LLM, puis committer les fichiers produits.
