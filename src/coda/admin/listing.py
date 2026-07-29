"""Pagination + header sorting shared by every list view.

A list route declares which columns are sortable (label -> ORM column), then
calls :func:`paginate` (entities) or :func:`paginate_rows` (column tuples). The
returned :class:`Page` carries the rows plus the state templates need to draw
sort headers and prev/next controls. URLs are kept stable by round-tripping
``q``/``sort``/``dir``/``page`` plus any route-specific filter params
(``Page.extra``) through the query string.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from math import ceil
from typing import Any, Mapping
from urllib.parse import urlencode

from sqlalchemy import Select, asc, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

PER_PAGE = 50


@dataclass(frozen=True)
class Page:
    items: list[Any]
    total: int
    page: int
    per_page: int
    sort: str
    dir: str
    q: str
    path: str
    # Route-specific filter params (mode, difficulty, gaps, …). Carried through
    # every generated URL so clicking a sort header or Next keeps the filters.
    # A value may be a list: multi-select filters repeat their key.
    extra: Mapping[str, str | list[str]] = field(default_factory=dict)

    @property
    def pages(self) -> int:
        return max(1, ceil(self.total / self.per_page))

    @property
    def has_prev(self) -> bool:
        return self.page > 1

    @property
    def has_next(self) -> bool:
        return self.page < self.pages

    @property
    def start(self) -> int:
        return 0 if self.total == 0 else (self.page - 1) * self.per_page + 1

    @property
    def end(self) -> int:
        return min(self.total, self.page * self.per_page)

    def url(self, *, sort: str | None = None, page: int | None = None) -> str:
        """Build a list URL, flipping direction when re-clicking the active sort."""
        params: dict[str, Any] = {"q": self.q} if self.q else {}
        params.update(self.extra)
        new_sort = sort or self.sort
        if sort and sort == self.sort:
            new_dir = "asc" if self.dir == "desc" else "desc"
        else:
            new_dir = self.dir if not sort else "asc"
        params["sort"] = new_sort
        params["dir"] = new_dir
        params["page"] = page or (1 if sort else self.page)
        return f"{self.path}?{urlencode(params, doseq=True)}"

    def arrow(self, key: str) -> str:
        """Sort indicator for a header (empty unless it's the active column)."""
        if key != self.sort:
            return ""
        return " ↑" if self.dir == "asc" else " ↓"


async def _window(
    session: AsyncSession,
    base: Select,
    *,
    request,
    columns: Mapping[str, Any],
    default_sort: str,
    path: str,
    q: str,
    extra: Mapping[str, str] | None,
) -> tuple[Select, Page]:
    """Resolve sort/direction/page from the query string, count the full result,
    and return the windowed statement alongside an item-less :class:`Page`."""
    params = request.query_params
    sort = params.get("sort") or default_sort
    if sort not in columns:
        sort = default_sort
    direction = params.get("dir", "asc")
    if direction not in ("asc", "desc"):
        direction = "asc"
    try:
        page = max(1, int(params.get("page", 1)))
    except ValueError:
        page = 1

    total = await session.scalar(
        select(func.count()).select_from(base.order_by(None).subquery())
    )
    order = (asc if direction == "asc" else desc)(columns[sort])
    stmt = base.order_by(order).offset((page - 1) * PER_PAGE).limit(PER_PAGE)
    meta = Page(
        items=[], total=total or 0, page=page, per_page=PER_PAGE,
        sort=sort, dir=direction, q=q, path=path, extra=dict(extra or {}),
    )
    return stmt, meta


async def paginate(
    session: AsyncSession,
    base: Select,
    *,
    request,
    columns: Mapping[str, Any],
    default_sort: str,
    path: str,
    q: str = "",
    extra: Mapping[str, str] | None = None,
) -> Page:
    """Sort + window ``base`` (a column-less SELECT of one entity) into a
    :class:`Page` of that entity."""
    stmt, meta = await _window(
        session, base, request=request, columns=columns,
        default_sort=default_sort, path=path, q=q, extra=extra,
    )
    return replace(meta, items=list((await session.scalars(stmt)).all()))


async def paginate_rows(
    session: AsyncSession,
    base: Select,
    *,
    request,
    columns: Mapping[str, Any],
    default_sort: str,
    path: str,
    q: str = "",
    extra: Mapping[str, str] | None = None,
) -> Page:
    """Sort + window a multi-entity ``base`` into a :class:`Page` of Row tuples."""
    stmt, meta = await _window(
        session, base, request=request, columns=columns,
        default_sort=default_sort, path=path, q=q, extra=extra,
    )
    return replace(meta, items=list((await session.execute(stmt)).all()))
