"""What an owner op receives and returns.

Nothing here imports hikari: an op decides *what happened*, the ``/run``
extension decides how it is rendered.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class OpRequest:
    """One submitted line, already tokenized, minus the verb."""

    args: list[str]
    invoker_id: int


@dataclass(frozen=True, slots=True)
class ConfirmAction:
    """A destructive step held behind a button.

    ``run`` opens its own database session. It fires up to a minute after the
    op returned, by which point any session the op held is closed.
    """

    prompt: str
    label: str
    run: Callable[[], Awaitable[str]]


@dataclass(frozen=True, slots=True)
class OpResult:
    text: str
    confirm: ConfirmAction | None = None


@dataclass(frozen=True, slots=True)
class Op:
    name: str
    summary: str
    usage: tuple[str, ...]
    handler: Callable[[OpRequest], Awaitable[OpResult]]
    # Completions for the verb's own arguments, without the verb itself.
    complete: Callable[[Sequence[str]], list[str]] | None = field(default=None)
