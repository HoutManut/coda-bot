"""``config`` -- bot-wide settings, read and written at ``Scope.GLOBAL``.

The only consumer that reads REGISTRY unfiltered; that is what the owner
surface is for. Per-scope writes stay on ``/config user|channel|server``, and
"what applies in this context" stays on ``/config view`` -- both a different
question from the bot-wide value this verb reads and writes.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from coda.db.session import async_session
from coda.ops.types import ConfirmAction, Op, OpRequest, OpResult
from coda.settings import REGISTRY, ConfigService, Scope, parse_value
from coda.settings.service import GLOBAL_SCOPE_ID

USAGE = (
    "`config list` -- every bot-wide setting",
    "`config get <key>`",
    "`config set <key> <value>`",
    "`config reset <key>` -- back to the built-in default",
)

_settings = ConfigService()


async def _list() -> OpResult:
    async with async_session() as db:
        stored = await _settings.all_at_scope(db, Scope.GLOBAL, GLOBAL_SCOPE_ID)
    lines = [
        f"**{name}**: `{stored[name]}`" if name in stored else f"**{name}**: `{defn.default}` *(default)*"
        for name, defn in REGISTRY.items()
    ]
    return OpResult("\n".join(lines))


async def _get(key: str) -> OpResult:
    defn = REGISTRY[key]
    async with async_session() as db:
        stored = await _settings.get_at_scope(db, key, Scope.GLOBAL, GLOBAL_SCOPE_ID)
    current = f"`{stored}`" if stored is not None else "*unset*"
    return OpResult(
        f"**{key}** — {defn.description}\n"
        f"bot-wide: {current}\nbuilt-in default: `{defn.default}`"
    )


async def _set(key: str, raw: str, invoker_id: int) -> OpResult:
    defn = REGISTRY[key]
    if Scope.GLOBAL not in defn.settable_scopes:
        return OpResult(f"**{key}** has no bot-wide scope.")
    try:
        value: Any = parse_value(defn, raw)
    except ValueError as err:
        return OpResult(str(err))
    async with async_session() as db:
        await _settings.set_value(db, key, Scope.GLOBAL, GLOBAL_SCOPE_ID, value, invoker_id)
    return OpResult(f"**{key}** is now `{value}` bot-wide.")


def _reset(key: str) -> OpResult:
    async def run() -> str:
        async with async_session() as db:
            await _settings.reset_value(db, key, Scope.GLOBAL, GLOBAL_SCOPE_ID)
        return f"**{key}** is back to its built-in default, `{REGISTRY[key].default}`."

    return OpResult(
        f"Reset **{key}** bot-wide? It goes back to `{REGISTRY[key].default}`.",
        confirm=ConfirmAction(prompt=f"Reset {key}", label="Reset to default", run=run),
    )


async def _run(req: OpRequest) -> OpResult:
    if not req.args:
        return OpResult("\n".join(USAGE))
    verb, *rest = req.args

    if verb == "list":
        return await _list()
    if verb not in ("get", "set", "reset"):
        return OpResult(f"Unknown config verb `{verb}`.\n" + "\n".join(USAGE))
    if not rest:
        return OpResult(f"`config {verb}` needs a key.")

    key = rest[0]
    if key not in REGISTRY:
        return OpResult(f"Unknown setting `{key}`.")
    if verb == "get":
        return await _get(key)
    if verb == "reset":
        return _reset(key)
    if len(rest) < 2:
        return OpResult(f"`config set {key}` needs a value.")
    return await _set(key, " ".join(rest[1:]), req.invoker_id)


def _complete(args: Sequence[str]) -> list[str]:
    if len(args) <= 1:
        typed = args[0] if args else ""
        return [verb for verb in ("get", "set", "reset", "list") if verb.startswith(typed)]
    verb = args[0]
    if verb not in ("get", "set", "reset"):
        return []
    if len(args) == 2:
        return [f"{verb} {key}" for key in REGISTRY if key.startswith(args[1])]
    if verb != "set" or len(args) > 3:
        return []
    key = args[1]
    defn = REGISTRY.get(key)
    choices = defn.choices if defn else None
    if choices is None:
        return []
    return [f"set {key} {choice}" for choice in choices if choice.startswith(args[2])]


OP = Op(
    name="config",
    summary="Bot-wide settings",
    usage=USAGE,
    handler=_run,
    complete=_complete,
)
