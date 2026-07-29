"""Shared declarative base for all ORM models.

Every model subclasses :class:`Base` so a single ``Base.metadata`` describes the
whole schema — Alembic autogenerate reads it, and nothing else creates tables.
"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
