"""Tests for the activities framework registry (Phase 7A)."""

from __future__ import annotations

import pytest

import activities


@pytest.fixture
def clean_registry():
    """Snapshot and restore the global registry around a test."""
    saved = dict(activities._REGISTRY)
    saved_flag = activities._discovered
    activities._REGISTRY.clear()
    activities._discovered = True  # skip auto-discovery; test controls contents
    try:
        yield activities._REGISTRY
    finally:
        activities._REGISTRY.clear()
        activities._REGISTRY.update(saved)
        activities._discovered = saved_flag


class _Runnable:
    slug = "dummy-run"
    name = "Dummy Runnable"
    description = "a runnable test activity"

    def setup(self, arm):  # noqa: D102
        pass

    def run(self, arm):  # noqa: D102
        pass

    def cleanup(self, arm):  # noqa: D102
        pass


class _Interactive(_Runnable):
    slug = "dummy-game"
    name = "Dummy Game"
    description = "an interactive test activity"

    def start(self, arm):  # noqa: D102
        return {}

    def human_move(self, arm, **action):  # noqa: D102
        return {}

    def state(self):  # noqa: D102
        return {}


def test_register_and_get(clean_registry):
    activities.register_activity(_Runnable)
    assert activities.get_activity("dummy-run") is _Runnable


def test_get_unknown_raises(clean_registry):
    with pytest.raises(KeyError):
        activities.get_activity("nope")


def test_register_requires_slug(clean_registry):
    class NoSlug:
        slug = ""
        name = "x"
        description = "y"

    with pytest.raises(ValueError):
        activities.register_activity(NoSlug)


def test_duplicate_slug_rejected(clean_registry):
    activities.register_activity(_Runnable)

    class Other:
        slug = "dummy-run"
        name = "other"
        description = "z"

    with pytest.raises(ValueError):
        activities.register_activity(Other)


def test_list_activities_metadata(clean_registry):
    activities.register_activity(_Runnable)
    activities.register_activity(_Interactive)
    listed = {a["slug"]: a for a in activities.list_activities()}
    assert listed["dummy-run"]["interactive"] is False
    assert listed["dummy-game"]["interactive"] is True
    assert listed["dummy-run"]["name"] == "Dummy Runnable"


def test_is_interactive_distinguishes():
    assert activities.is_interactive(_Interactive) is True
    assert activities.is_interactive(_Interactive()) is True
    assert activities.is_interactive(_Runnable) is False
    assert activities.is_interactive(_Runnable()) is False


def test_discover_is_idempotent_and_safe():
    # Should import sibling modules without raising, even if none exist yet.
    activities.discover()
    activities.discover()
