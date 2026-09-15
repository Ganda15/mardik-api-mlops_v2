# Mardik — livrer et piloter la nouvelle version

*Brief de création, Phase 4 — chaîne LLMOps & observabilité.*

Mardik analyse des contrats commerciaux avec un LLM et en liste les clauses.
La **v1** tourne en production et un client interne (`scripts/client_v1.py`)
en dépend. Le client juridique veut une **v2** : contrats longs sans
troncature, score de confiance — livrée par une chaîne automatique,
déployée progressivement, et pilotable (rollback en une opération).

Lisez d'abord `docs/besoin_client.md`. Puis `docs/schema_remediation.md`.

## Règles du jeu

- **`app/api_v1.py` est intouchable.** Le client historique doit continuer
  de fonctionner tel quel, à chaque commit. C'est le seul test vert au départ.
- **Une version du modèle est un bundle de configuration.** Voyez
  `models/v1/config.yaml` : modèle de base + prompt + paramètres + schéma de
  sortie + stratégie. La v2 (`models/v2/config.yaml`) est le même client LLM
  avec un autre bundle. C'est ce bundle qu'on étiquette, qu'on livre et qu'on
  rollback.
- **Les modèles sont de vrais LLM.** Vraie latence, vrai non-déterminisme,
  vrai coût. La troncature de la v1 sur les contrats longs est une conséquence
  réelle de sa config, pas une simulation.
- **La dérive est injectée par un proxy** (`ops/drift_proxy.py`), pas par le
  modèle : `DRIFT=latence|erreurs|score`, pilotable à chaud. C'est ce qui rend
  la démo de fin de phase commandable.
- **`MOCK=on` est réservé à la CI.** Les gates doivent tourner vite et
  gratuitement à chaque fusion : en CI, le client rejoue des réponses
  enregistrées (`eval/fixtures/`). En salle, `MOCK=off`.
- **Les modules à construire sont des stubs** qui lèvent `NotImplementedError`
  avec, en docstring, le contrat attendu. Les tests d'acceptance sont fournis
  et rouges : le brief se joue du rouge au vert.

## Mise en route

```bash
make install                 # uv sync
cp .env.example .env         # choisir le fournisseur : ollama (gratuit) ou azure (clé API)
ollama pull llama3.2:3b      # si LLM_PROVIDER=ollama
make up                      # app :8000, proxy de dérive :8080, dashboard :8501
```

Sans docker : `make proxy` dans un terminal, `make serve` dans un autre.

```bash
# la v1 répond et analyse un contrat court
curl -s localhost:8000/v1/analyse -H 'content-type: application/json' \
     -d @<(jq -Rs '{texte: .}' eval/contrats/c01.txt) | jq

# la douleur de départ : un contrat long est tronqué
curl -s localhost:8000/v1/analyse -H 'content-type: application/json' \
     -d @<(jq -Rs '{texte: .}' eval/contrats/c12.txt) | jq '.tronque, .clauses'

python scripts/client_v1.py  # le client historique : vert
make test-acceptance         # 9 rouges, 1 vert : l'état attendu du lundi matin
```

## Commandes

| Commande | Quoi |
|---|---|
| `make up` / `make down` | app + proxy + dashboard (docker compose) |
| `make test` | tout, en `MOCK=on` |
| `make test-integration` | les tests hérités de la remédiation (verts) |
| `make test-acceptance` | les 10 tests du brief |
| `make eval VERSION=v2` | le gate d'évaluation sur le **vrai** modèle (`ARGS="--essais 3"`) |
| `make traffic MODE=derive-score` | trafic sur la gateway + dérive commandée (`normal`, `derive-latence`, `erreurs`) |
| `make dashboard` | tableau de bord (texte) ; `DASH=serve` pour la page HTML |
| `make ci` | l'équivalent local du workflow GitHub |
| `make fixtures` | (ré)enregistre les fixtures `MOCK` avec le vrai modèle |

Déploiement : `python -m ops.deploy publier v2.0.0 | canary v2.0.0 --pourcentage 10 | promouvoir v2.0.0 | rollback | surveiller --boucle`.

## Arborescence

```
app/          main.py (FastAPI), api_v1.py [INTOUCHABLE], api_v2.py [STUB], gateway.py [STUB],
              llm_client.py [FOURNI], telemetry.py [FOURNI], pipeline/ [STUBS]
models/       v1/config.yaml [FOURNI], v2/config.yaml [À COMPLÉTER]
eval/         contrats/ (12 contrats, 3 longs), attendus.jsonl, fixtures/ (MOCK), run_eval.py [STUB], history.jsonl [GÉNÉRÉ]
ops/          drift_proxy.py [FOURNI], registry/ [FOURNI], deploy.py [STUB], dashboard.py [STUB]
scripts/      client_v1.py [FOURNI], traffic_sim.py [FOURNI]
tests/        integration/ (verts), acceptance/ (10 tests du brief)
docs/         besoin_client.md, schema_remediation.md, exploitation.md [À RÉDIGER]
.github/      workflows/llmops.yml [TEMPLATE] — étapes posées, gates en TODO
```

## Les chantiers

1. **Le bundle v2** — `models/v2/config.yaml` : stratégie, schéma de sortie, paramètres.
   *Qu'est-ce qui, dans ce fichier, fait qu'une version est une version ?*
2. **Le pipeline v2** — `app/pipeline/` (découpage, extraction, consolidation, confiance)
   et `app/api_v2.py`. Sans casser `/v1`.
3. **Le gate d'évaluation** — `eval/run_eval.py` : une note par version, sur les 12
   contrats annotés, avec latence et coût. *Deux exécutions ne donnent pas la même
   note : que faites-vous ?*
4. **La chaîne** — `ops/deploy.py` (étiquetage, canary, promotion, rollback,
   surveillance) et `.github/workflows/llmops.yml`. *Que peut vérifier la CI sans
   le vrai modèle ?*
5. **Le pilotage** — `app/gateway.py` (routeur canary), `ops/dashboard.py`,
   `docs/exploitation.md`.

Démo de fin : `make traffic MODE=derive-score` en live → dérive vue au tableau
de bord → rollback → entrée au journal.

## Coût et non-déterminisme

Le gate rejoue 12 contrats à chaque exécution. Avec plusieurs équipes qui
poussent souvent : Ollama en local, ou un plafond — le gate en CI tourne en
`MOCK=on`, seul le gate « de release » appelle le vrai modèle. Et deux
exécutions du gate ne donnent pas la même note : c'est le sujet (seed,
température, moyenne sur *n* essais, seuil avec marge). Ne le « corrigez »
pas : concevez avec.
