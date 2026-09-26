"""Tournaments -- matches, rounds, and the policy layer over ``play_scores``.

The module never calls the lowiro API. It declares hot windows and reads rows
the poller wrote for an unrelated reason, which is what makes it testable by
inserting scores: no HTTP, no ``sid``, no ``bot_account_id`` anywhere in it.

``hikari`` appears only in ``render.py``, ``transport.py`` and ``board.py``,
which sit at the Discord edge -- the same split ``chardle/`` draws between its
services and its transport.
"""

from __future__ import annotations
