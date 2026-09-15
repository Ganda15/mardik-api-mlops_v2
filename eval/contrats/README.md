# Contrats de démonstration

12 contrats de prestations de services en texte brut (fictifs, générés), de
2 à 40 pages. Trois sont longs (`c07` 30 p., `c10` 35 p., `c12` 40 p.) : leurs
clauses importantes (résiliation, droit applicable…) sont en fin de document,
au-delà de la fenêtre de contexte de la v1.

Les clauses attendues par contrat sont dans `../attendus.jsonl` :

```json
{"contrat_id": "c07", "pages": 30, "clauses_attendues": ["durée", "résiliation", ...], "seuil_note": 0.8}
```
