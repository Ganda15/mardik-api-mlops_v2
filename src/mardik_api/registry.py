"""Versioned artifact registry for released models (mock, file-backed)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class Version:
    tag: str
    commit: str


class Registry:
    """Stores released model versions and tracks which one is active."""

    def __init__(self, root: Any | None = None) -> None:
        self.root = root

    def register(self, commit: str, artifact: dict[str, Any] | None = None) -> Version:
        raise NotImplementedError

    def list_versions(self) -> list[Version]:
        raise NotImplementedError

    def set_active(self, tag: str) -> None:
        raise NotImplementedError

    def active_version(self) -> Version | None:
        raise NotImplementedError

    def rollback(self) -> None:
        raise NotImplementedError
