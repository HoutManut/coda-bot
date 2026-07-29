"""Local web admin for the Arcaea catalog.

A localhost-only FastAPI + Jinja2 + htmx app for editing the catalog the bot
reads. It reuses the bot's ORM models, async session, effective-value
resolution, and the encode/decode helpers, so what it writes is exactly what the
bot expects. Not for remote exposure — bind ``127.0.0.1``.

Run: ``uv run python -m coda.admin`` (or ``uvicorn coda.admin.app:app``).
"""
