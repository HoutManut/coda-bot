from __future__ import annotations

from typing import Any

from sqlalchemy import delete, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from coda.settings.model import ConfigValue
from coda.settings.registry import REGISTRY
from coda.settings.types import Scope

GLOBAL_SCOPE_ID = 0


class ConfigService:
    async def resolve(
        self,
        session: AsyncSession,
        key: str,
        *,
        guild_id: int | None,
        channel_id: int,
        user_id: int,
        is_dm: bool,
    ) -> Any:
        defn = REGISTRY[key]
        chain = defn.dm_chain if is_dm else defn.guild_chain

        scope_id_map: dict[Scope, int] = {Scope.GLOBAL: GLOBAL_SCOPE_ID}
        if not is_dm:
            if guild_id is not None:
                scope_id_map[Scope.GUILD] = guild_id
            scope_id_map[Scope.CHANNEL] = channel_id
        scope_id_map[Scope.USER] = user_id

        conditions = [
            (ConfigValue.scope == s.value) & (ConfigValue.scope_id == scope_id_map[s])
            for s in chain
            if s in scope_id_map
        ]
        if not conditions:
            return defn.default

        result = await session.execute(
            select(ConfigValue)
            .where(ConfigValue.key == key)
            .where(or_(*conditions))
        )
        by_scope = {row.scope: row.value["v"] for row in result.scalars()}

        for s in chain:
            if s.value in by_scope:
                return by_scope[s.value]
        return defn.default

    async def get_at_scope(
        self,
        session: AsyncSession,
        key: str,
        scope: Scope,
        scope_id: int,
    ) -> Any | None:
        result = await session.execute(
            select(ConfigValue).where(
                ConfigValue.key == key,
                ConfigValue.scope == scope.value,
                ConfigValue.scope_id == scope_id,
            )
        )
        row = result.scalar_one_or_none()
        return row.value["v"] if row is not None else None

    async def set_value(
        self,
        session: AsyncSession,
        key: str,
        scope: Scope,
        scope_id: int,
        value: Any,
        set_by: int,
    ) -> None:
        from sqlalchemy import func

        stmt = (
            pg_insert(ConfigValue)
            .values(
                key=key,
                scope=scope.value,
                scope_id=scope_id,
                value={"v": value},
                set_by=set_by,
            )
            .on_conflict_do_update(
                index_elements=["key", "scope", "scope_id"],
                set_={
                    "value": {"v": value},
                    "set_by": set_by,
                    "set_at": func.now(),
                },
            )
        )
        await session.execute(stmt)
        await session.commit()

    async def reset_value(
        self,
        session: AsyncSession,
        key: str,
        scope: Scope,
        scope_id: int,
    ) -> None:
        await session.execute(
            delete(ConfigValue).where(
                ConfigValue.key == key,
                ConfigValue.scope == scope.value,
                ConfigValue.scope_id == scope_id,
            )
        )
        await session.commit()

    async def all_at_scope(
        self,
        session: AsyncSession,
        scope: Scope,
        scope_id: int,
    ) -> dict[str, Any]:
        result = await session.execute(
            select(ConfigValue).where(
                ConfigValue.scope == scope.value,
                ConfigValue.scope_id == scope_id,
            )
        )
        return {row.key: row.value["v"] for row in result.scalars()}
