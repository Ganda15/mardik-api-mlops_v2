"""Mardik — analyse de contrats par LLM.

Charge ``.env`` (sans écraser les variables déjà définies) dès que le paquet
est importé : l'app, le proxy, l'éval et les scripts lisent la même config.
"""
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)
