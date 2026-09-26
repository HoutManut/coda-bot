"""``spoiler`` -- which game versions render blurred.

Flagging a version blurs every chart on it across ``/song``, ``/score``,
``/calc``, ``/recent`` and the live poster, and flips those commands' ephemeral
default. It hides nothing from search: see ``catalog/spoilers.py``.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import func, select

from coda.catalog import spoilers
from coda.catalog.query import version_value
from coda.db.models import Song, SongDifficulty
from coda.db.session import async_session
from coda.ops.types import ConfirmAction, Op, OpRequest, OpResult

USAGE = (
    "`spoiler list` -- every flagged version",
    "`spoiler add <version>` -- blur every chart on it",
    "`spoiler remove <version>` -- unflag it, revealing every chart on it",
)


def _list() -> OpResult:
    flagged = sorted(spoilers.flagged())
    if not flagged:
        return OpResult("No version is flagged as a spoiler.")
    lines = [f"**{version}**" for version in flagged]
    return OpResult("\n".join(["**Spoilered versions**", *lines]))


async def _chart_count(db, version: str) -> int:
    """How many charts sit on this effective version."""
    return await db.scalar(
        select(func.count())
        .select_from(SongDifficulty)
        .join(Song, Song.song_id == SongDifficulty.song_id)
        .where(func.coalesce(SongDifficulty.version, Song.version) == version)
    )


async def _add(version: str, invoker_id: int) -> OpResult:
    async with async_session() as db:
        charts = await _chart_count(db, version)
        # A typo that flags nothing looks identical to a version that has not
        # shipped yet, and both silently blur nothing -- so refuse at the edge.
        if charts == 0:
            return OpResult(f"No charts are on version **{version}**.")
        if not await spoilers.add(db, version, invoker_id):
            return OpResult(f"**{version}** is already flagged.")
    return OpResult(f"**{version}** is now a spoiler — {charts} chart(s) blurred.")


def _remove(version: str) -> OpResult:
    async def run() -> str:
        async with async_session() as db:
            if not await spoilers.remove(db, version):
                return f"**{version}** was not flagged."
        return f"**{version}** is no longer a spoiler."

    if version not in spoilers.flagged():
        return OpResult(f"**{version}** is not flagged.")
    return OpResult(
        f"Unflag **{version}**? Every chart on it renders in the clear from then on.",
        confirm=ConfirmAction(
            prompt=f"Unflag {version}", label="Unflag", run=run
        ),
    )


async def _run(req: OpRequest) -> OpResult:
    if not req.args:
        return OpResult("\n".join(USAGE))
    verb, *rest = req.args

    if verb == "list":
        return _list()
    if verb not in ("add", "remove"):
        return OpResult(f"Unknown spoiler verb `{verb}`.\n" + "\n".join(USAGE))
    if not rest:
        return OpResult(f"`spoiler {verb}` needs a version.")

    try:
        version = version_value(rest[0])
    except ValueError as err:
        return OpResult(str(err))
    if verb == "add":
        return await _add(version, req.invoker_id)
    return _remove(version)


def _complete(args: Sequence[str]) -> list[str]:
    """Completions come from the cached flagged set -- this runs synchronously
    and cannot query, so ``add`` offers nothing and a version is typed out."""
    if len(args) <= 1:
        typed = args[0] if args else ""
        return [verb for verb in ("list", "add", "remove") if verb.startswith(typed)]
    if args[0] != "remove" or len(args) > 2:
        return []
    return [
        f"remove {version}"
        for version in sorted(spoilers.flagged())
        if version.startswith(args[1])
    ]


OP = Op(
    name="spoiler",
    summary="Versions rendered as spoilers",
    usage=USAGE,
    handler=_run,
    complete=_complete,
)
