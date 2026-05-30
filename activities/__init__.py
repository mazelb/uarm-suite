"""Lightweight plugin framework for arm-driven activities.

An *activity* is anything the arm can do on its own — drawing a shape, playing
a game. Activities talk to the arm only through the high-level :class:`UArm`
controller (never the bus or hardware libraries directly), so they stay
portable across sim and hardware.

Two flavours, both discovered by the same registry:

* **Runnable** activities (e.g. draw-shapes) implement :class:`ActivityBase`.
  The caller runs ``setup`` -> ``run`` -> ``cleanup`` to completion; the server
  does this in a background thread.
* **Interactive** activities (e.g. tic-tac-toe) additionally implement
  :class:`InteractiveActivity`. They hold session state and are driven turn by
  turn via ``start`` / ``human_move`` / ``state``.

Discovery is by directory scan: :func:`discover` imports every sibling module
in this package, which triggers the ``@register_activity`` decorators. Adding a
new activity is therefore just dropping a module in ``activities/`` — no central
list to edit.
"""

from __future__ import annotations

import importlib
import pkgutil
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from arm import UArm


@runtime_checkable
class ActivityBase(Protocol):
    """A runnable arm activity."""

    slug: str  # url-safe identifier, e.g. "tic-tac-toe"
    name: str  # display name, e.g. "Tic-Tac-Toe"
    description: str  # one-line summary

    def setup(self, arm: UArm) -> None:
        """Prepare the arm (home, draw a frame, etc.). May be a no-op."""
        ...

    def run(self, arm: UArm) -> None:
        """Execute the activity to completion."""
        ...

    def cleanup(self, arm: UArm) -> None:
        """Restore a safe state. May be a no-op."""
        ...


@runtime_checkable
class InteractiveActivity(ActivityBase, Protocol):
    """A turn-based activity driven by a human between arm moves."""

    def start(self, arm: UArm) -> dict:
        """Begin a fresh session and return the initial state dict."""
        ...

    def human_move(self, arm: UArm, **action: object) -> dict:
        """Apply one human action, let the arm respond, return new state."""
        ...

    def state(self) -> dict:
        """Return the current state dict without changing anything."""
        ...


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_REGISTRY: dict[str, type[ActivityBase]] = {}
_discovered = False


def register_activity(cls: type[ActivityBase]) -> type[ActivityBase]:
    """Class decorator: add an activity class to the registry by its ``slug``."""
    slug = getattr(cls, "slug", None)
    if not slug:
        raise ValueError(f"{cls.__name__} must define a non-empty 'slug'")
    if slug in _REGISTRY and _REGISTRY[slug] is not cls:
        raise ValueError(f"duplicate activity slug {slug!r}")
    _REGISTRY[slug] = cls
    return cls


def discover() -> None:
    """Import every module in this package so decorators register their classes.

    Idempotent: safe to call repeatedly (e.g. on each server start).
    """
    global _discovered
    for mod in pkgutil.iter_modules(__path__):
        if mod.name.startswith("_"):
            continue
        importlib.import_module(f"{__name__}.{mod.name}")
    _discovered = True


def _ensure_discovered() -> None:
    if not _discovered:
        discover()


_INTERACTIVE_METHODS = ("start", "human_move", "state")


def is_interactive(obj: object) -> bool:
    """True if the activity class or instance supports the interactive protocol.

    Checked structurally with ``hasattr`` rather than ``issubclass``: a
    ``runtime_checkable`` Protocol carrying data members (``slug`` etc.) cannot
    be used with ``issubclass``.
    """
    return all(hasattr(obj, m) for m in _INTERACTIVE_METHODS)


def get_activity(slug: str) -> type[ActivityBase]:
    """Return the activity class registered under ``slug``."""
    _ensure_discovered()
    try:
        return _REGISTRY[slug]
    except KeyError:
        raise KeyError(f"unknown activity {slug!r}") from None


def list_activities() -> list[dict]:
    """Return metadata for every registered activity, sorted by slug."""
    _ensure_discovered()
    return [
        {
            "slug": cls.slug,
            "name": cls.name,
            "description": cls.description,
            "interactive": is_interactive(cls),
        }
        for slug, cls in sorted(_REGISTRY.items())
    ]


__all__ = [
    "ActivityBase",
    "InteractiveActivity",
    "register_activity",
    "discover",
    "is_interactive",
    "get_activity",
    "list_activities",
]
