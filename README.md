# Mardik Model API & MLOps Chain

API HTTP qui expose le modèle de classification du sentiment des avis clients de
Mardik (Kimi-K2.6, Azure AI Inference), accompagnée d'une chaîne de livraison qui
teste, étiquette et publie automatiquement chaque nouvelle version — avec retour
arrière.

## Features

- Endpoint `POST /predict` : prend un texte d'avis et renvoie une prédiction (étiquette + score), l'identité et la version du modèle.
- Validation des entrées : les requêtes mal formées reçoivent une erreur explicite.
- Registre d'artefacts versionné : chaque version livrée est étiquetée et conservée.
- Chaîne de livraison : build → tests → publication d'une version étiquetée.
- Retour arrière : réactivation de la version précédente en cas de livraison défaillante.

## Stack

- Python 3.11, géré avec `uv`
- FastAPI + Uvicorn, Pydantic 2
- LangChain 0.3 + `langchain-azure-ai` (modèle Kimi-K2.6)
- Registre d'artefacts S3-compatible (MinIO via docker-compose)
- pytest 8

## Setup

```bash
make install              # uv sync — install dependencies
cp .env.example .env      # then fill in the values
make up                   # docker compose up -d (API + artifact registry)
make test                 # run the acceptance suite
make serve                # run the API locally (uvicorn, port 8000)
```

API : http://localhost:8000 — `GET /health` pour la sonde, `POST /predict` pour une prédiction.

## Layout

```
src/mardik_api/
  app.py        Application FastAPI et routes HTTP
  model.py      Enveloppe du modèle (predict) + dépendance get_model
  schemas.py    Contrat d'entrée/sortie de l'API
  registry.py   Registre versionné des artefacts de modèle
  pipeline.py   Chaîne de livraison (build, test, release, rollback)
  llm.py        Fabrique du client Azure (Kimi-K2.6)
tests/acceptance/  Suite d'acceptance (contrat d'API + chaîne MLOps)
rollback/          Documentation de versionnage et de retour arrière
expression_besoin.md  Expression de besoin client à analyser
docker-compose.yml    API + registre d'artefacts (MinIO)
Dockerfile            Image de l'API
```

## Useful commands

```bash
make fmt        # ruff format + autofix
make lint       # ruff check
make typecheck  # mypy
make down       # stop docker services
```

## License

MIT

## Contact

es.agwu.19@eigsi.fr
