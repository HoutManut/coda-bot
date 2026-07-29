"""Observability wiring: one central logging setup over stdlib ``logging``.

Call sites are unchanged plain stdlib (``logging.getLogger(__name__)``); this
package only configures where records go. Per-record steering rides on ``extra``:
``extra={"discord": True}`` forces a record onto the discord channel below its
threshold, ``extra={"discord": False}`` holds it back (same for ``console``/``file``).
"""

from __future__ import annotations

from coda.logging.setup import configure_logging, start_discord, stop_discord

__all__ = ["configure_logging", "start_discord", "stop_discord"]
