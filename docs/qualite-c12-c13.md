# C12 et C13 — couverture de tests et test des données

> Référentiel RNCP37827, pilier 4 (C12) et pilier 5 (C13). Fermé le 23/09/2026, après la réponse du chef
> de projet à la question d'un camarade (« pas d'entraînement/déploiement scikit-learn nécessaire sur un
> parcours agentique ; les tests automatisés + l'explication des pratiques suffisent ») — voir
> `materiel-reunion-2026-09-23\INDEX.md`. Ce document est l'explication écrite que cette réponse demande.

## C12 — couverture de tests, cible écrite et mesurée

**Ce que le critère demande.** Les cas à tester listés, une couverture cible **établie**, et la preuve
qu'elle est atteinte.

**Cas testés.** Chaque brique du dépôt (bundle, découpage, extraction, consolidation, score, API v1/v2,
gateway, gate d'évaluation, déploiement, sécurité, signaux, watcher, pilotage, enrichissement, seuils,
détecteur, test des données) a son fichier `tests/test_*.py`, écrit **avant** le code (TDD, tout le
dépôt). Périmètre couvert : `app/`, `ops/`, `eval/` — le code applicatif, le pipeline du modèle, la chaîne
de pilotage et l'évaluation. Hors périmètre : `scripts/` (outillage de démonstration, pas de logique
métier), `models/` (données de configuration, pas du code).

**Mesuré le 23/09/2026** (`uv run pytest --cov=app --cov=ops --cov=eval --cov-report=term-missing`) :

| Périmètre | Instructions | Manquées | Couverture |
|---|---|---|---|
| `app/` | 686 | 91 | 87 % |
| `ops/` | 862 | 178 | 79 % |
| `eval/` | 213 | 38 | 82 % |
| **Total** | **1761** | **293** | **83 %** |

**Ce qui explique les points manquants.** Pas au hasard : `app/pipeline/decoupage.py`,
`consolidation.py`, `app/securite.py` — la logique testée en TDD — sont à **100 %**. Les fichiers les
plus bas (`ops/drift_proxy.py` 43 %, `ops/detecteur.py` 64 %, `ops/dashboard.py` 69 %) doivent
principalement leurs lignes manquantes à leur fonction `main()` — l'analyse d'arguments et le
branchement des sous-commandes, testés par des appels réels en ligne de commande dans certains fichiers
(`tests/test_ajuster_seuils.py`), pas systématiquement partout. C'est un choix assumé : la logique
métier est celle qui doit être fiable en TDD strict ; le squelette d'un `argparse` a un risque
d'erreur beaucoup plus faible.

**Cible : 80 %.** En dessous de la mesure du jour (83 %), avec de la marge pour ce déséquilibre connu
entre logique métier et code d'interface en ligne de commande — sans baisser l'exigence sur ce qui
compte. **Appliquée**, pas seulement écrite : `--cov-fail-under=80` dans le job `tests` de
`.github/workflows/llmops.yml` — une baisse de couverture fait échouer la chaîne, au même titre qu'un
test rouge.

```yaml
- name: Couverture (C12) — cible 80 %, mesurée 83 % le 23/09 ; échoue en dessous
  run: uv run pytest -q --cov=app --cov=ops --cov=eval --cov-report=term-missing --cov-fail-under=80
```

**Limite dite telle quelle.** Un pourcentage de lignes exécutées ne prouve pas qu'une assertion
pertinente a été faite sur chacune — c'est une mesure de **surface**, pas de qualité d'assertion. Le TDD
pratiqué brique par brique (le test écrit avant le code, vérifié rouge pour la bonne raison, puis vert)
est la garantie complémentaire, pas remplacée par ce chiffre.

## C13 — étape de test des données, intégrée à la chaîne

**Ce que le critère demande.** Une étape de test des **données** — pas seulement du code — intégrée à la
chaîne et sans erreur.

**Pourquoi maintenant.** Depuis la brique 17 (Chantier 2), `eval/attendus.jsonl` n'est plus écrit
seulement par un développeur qui le relit : la boucle d'enrichissement y verse des cas réels, étiquetés
par un juriste (`python -m ops.enrichissement ajouter`). Une ligne mal formée, un type de clause hors
vocabulaire, ou un contrat référencé mais absent doivent être trouvés **avant** le gate, avec un message
précis — pas laissés planter le gate plus loin sans dire pourquoi.

**Ce qui est vérifié**, `eval/valider_attendus.py` :

```python
def _valider_ligne(numero, brut, dossier_contrats, vus):
    item = json.loads(brut)                      # JSON valide, avec le numéro de ligne dans l'erreur
    for champ in ("contrat_id", "clauses_attendues"):
        if champ not in item:
            raise ErreurDonnees(f"ligne {numero} : champ manquant : {champ}")
    if item["contrat_id"] in vus:
        raise ErreurDonnees(f"ligne {numero} : doublon de contrat_id : {item['contrat_id']}")
    inconnues = [c for c in item["clauses_attendues"] if c not in TYPES_CLAUSES]
    if inconnues:
        raise ErreurDonnees(f"... type(s) de clause hors vocabulaire : {', '.join(inconnues)}")
    if not (dossier_contrats / f"{item['contrat_id']}.txt").is_file():
        raise ErreurDonnees(f"... sans fichier eval/contrats/{item['contrat_id']}.txt")
```

**Intégrée**, pas seulement écrite : une étape nommée dans le job `tests` de `llmops.yml`, avant les
tests d'intégration et d'acceptance — un jeu d'évaluation invalide bloque tout le reste, y compris le
gate, par la chaîne `needs:` déjà en place.

```yaml
- name: Test des données (C13) — eval/attendus.jsonl avant tout le reste
  run: uv run python -m eval.valider_attendus
```

**Preuve que ça mord** : une mutation en mémoire (vocabulaire des clauses vidé) fait échouer 5 des 9
tests du fichier — la validation dépend réellement du vocabulaire réel, pas d'un chemin qui ne teste
rien.
