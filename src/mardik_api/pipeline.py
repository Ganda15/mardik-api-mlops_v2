"""The MLOps delivery chain: build, test, tag, release, rollback."""
from __future__ import annotations

from .registry import Registry, Version


def run_release(commit: str, registry: Registry) -> Version:
    """Run the delivery chain for a merged commit and return the released version.

    A full run builds the model artifact, runs the test gate, registers a new
    tagged version and activates it.
    """
    raise NotImplementedError
