"""Poll keys -- what a poll cycle iterates, and what a refresh can target.

The two read paths have different units: the friend path polls a BOT ACCOUNT
(one ``/friend/me`` covers every player it holds), the own path polls a PLAYER
(one ``/user/me`` each). So a key is namespaced rather than a bare id -- the two
id spaces are unrelated and would collide.

Keys are constructed by the layer that owns the id (``sessions/pool.py`` for a
bot key, ``scores/`` for an own key) and treated as opaque everywhere else,
which is what keeps ``bot_account_id`` from leaking upward.
"""

from __future__ import annotations

BOT = "bot"
OWN = "own"

# (namespace, id) -- ("bot", bot_accounts.id) or ("own", arcaea_accounts.id).
type PollKey = tuple[str, int]
