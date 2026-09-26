"""The verb table, and the tokenize -> resolve -> dispatch path over it."""

from __future__ import annotations

import shlex

from coda.ops.config import OP as CONFIG_OP
from coda.ops.reconcile import OP as RECONCILE_OP
from coda.ops.spoiler import OP as SPOILER_OP
from coda.ops.types import Op, OpRequest, OpResult

# Discord's hard cap on autocomplete results, and on one choice's value.
MAX_SUGGESTIONS = 25
MAX_SUGGESTION_LENGTH = 100

OPS: dict[str, Op] = {op.name: op for op in (CONFIG_OP, RECONCILE_OP, SPOILER_OP)}


def tokenize(line: str) -> list[str]:
    """Split a submitted line. Raises ``ValueError`` on an unbalanced quote."""
    return shlex.split(line)


def help_text(op: Op | None = None) -> str:
    """Verb list, or one verb's grammar. The only documentation a free-text
    option can carry -- named options get theirs from Discord."""
    if op is not None:
        return f"**{op.name}** — {op.summary}\n" + "\n".join(op.usage)
    lines = [f"`{name}` — {known.summary}" for name, known in OPS.items()]
    return "\n".join(["**Verbs**", *lines, "", "`<verb> help` for one verb's grammar."])


async def dispatch(line: str, *, invoker_id: int) -> OpResult:
    """Run one submitted line. Every token is re-validated by the verb --
    autocomplete narrows nothing."""
    tokens = tokenize(line)
    if not tokens or tokens[0] == "help":
        return OpResult(help_text())

    op = OPS.get(tokens[0])
    if op is None:
        return OpResult(f"Unknown verb `{tokens[0]}`.\n\n{help_text()}")

    args = tokens[1:]
    if args and args[-1] == "help":
        return OpResult(help_text(op))
    return await op.handler(OpRequest(args=args, invoker_id=invoker_id))


def suggestions(line: str) -> list[str]:
    """Rebuilt full lines, because a chosen row replaces the whole option."""
    try:
        tokens = tokenize(line)
    except ValueError:
        return []

    typing_new_token = line.endswith(" ") or not line
    if not tokens or (len(tokens) == 1 and not typing_new_token):
        typed = tokens[0] if tokens else ""
        rows = [name for name in OPS if name.startswith(typed)]
    else:
        op = OPS.get(tokens[0])
        if op is None or op.complete is None:
            return []
        args = [*tokens[1:], ""] if typing_new_token else tokens[1:]
        rows = [f"{op.name} {tail}" for tail in op.complete(args)]

    return [row for row in rows if len(row) <= MAX_SUGGESTION_LENGTH][:MAX_SUGGESTIONS]
