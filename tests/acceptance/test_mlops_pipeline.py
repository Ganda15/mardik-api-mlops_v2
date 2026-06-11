"""Acceptance: the MLOps delivery chain releases and rolls back versions.

- Given a merged change, the chain tests and delivers a tagged version automatically.
- Given a faulty delivery, a rollback to the previous version is possible.
"""
from __future__ import annotations

from mardik_api.pipeline import run_release
from mardik_api.registry import Registry


def test_merge_triggers_tagged_release(tmp_path):
    registry = Registry(root=tmp_path)
    version = run_release(commit="abc123", registry=registry)

    assert version.tag
    active = registry.active_version()
    assert active is not None
    assert active.tag == version.tag
    assert active.commit == "abc123"


def test_faulty_delivery_can_rollback(tmp_path):
    registry = Registry(root=tmp_path)
    first = run_release(commit="c1", registry=registry)
    second = run_release(commit="c2", registry=registry)

    assert registry.active_version().tag == second.tag

    registry.rollback()

    assert registry.active_version().tag == first.tag
