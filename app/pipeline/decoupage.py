"""Découpage d'un contrat par clauses (étape *map* du map-reduce). [STUB]

Contrat attendu :

    decouper(texte: str, taille_max: int = 6000) -> list[Section]

* Une ``Section`` porte un ``titre`` (l'intitulé de l'article, ou ``"préambule"``),
  un ``texte`` et son ``indice`` (ordre dans le contrat).
* Le découpage suit les intitulés d'articles (« Article 3 — Résiliation »,
  « 3. Résiliation », « ARTICLE 3 : … »). Une section plus longue que
  ``taille_max`` est elle-même découpée en morceaux, sans couper une phrase.
* La concaténation des ``texte`` de toutes les sections doit couvrir tout le
  contrat : rien ne doit être perdu — c'est précisément ce que la v1 ne
  garantit pas.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Section:
    indice: int
    titre: str
    texte: str


def decouper(texte: str, taille_max: int = 6000) -> list[Section]:
    raise NotImplementedError("pipeline.decoupage.decouper — découper le contrat par clauses")
