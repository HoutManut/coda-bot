"""Wait lengths. Constants, not configuration.

Every wait ends early when the thing it waits for has happened -- the player
acts, everyone scores, everyone is Ready -- and the timeout is only the backstop
for a human who does not act. That is what makes these safe to pin: nobody
needs to tune a wait that ends the moment it is satisfied. A tunable timeout is
what you build when you cannot end the wait early, and it is a worse answer to
the same problem.
"""

from __future__ import annotations

# How long a pick/ban turn waits before it auto-acts at random.
TURN_SECONDS = 60

# How long a round's validity window stays open. FLAT, not derived from chart
# length: the window ends the moment both sides have scored, so it never has to
# be sized to fit two plays -- only to be long enough that a player who has not
# started yet is not cut off.
WINDOW_SECONDS = 300

# Observation slack past end_ms. Polling is discrete, so a play at end_ms - 1s
# may not be SEEN until after end_ms.
GRACE_SECONDS = 60

# The rest between a round being decided and the next chart being revealed. It
# begins once the scores are gathered and the winner is known, so it is a beat
# to read the result in -- NOT the song-select navigation budget the old 2t
# window needed, which WINDOW_SECONDS now contains outright.
#
# Long, because it is the only slack a match has. A window ends the moment both
# sides have scored, so a Bo3 that used to run on a 60 s break gave two players
# no room at all between three back-to-back charts. Nobody waits it out who does
# not want to: Ready from either surface ends it early.
BREAK_SECONDS = 300

# How often the sweep recomputes deadlines and redraws changed boards. Also the
# board's debounce: an ingest storm cannot edit the message faster than this.
TICK_SECONDS = 5
