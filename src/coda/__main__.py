"""Entry point."""

from __future__ import annotations

import hikari

from coda.bot import build


def main() -> None:
    bot = build()
    bot.run(
        activity=hikari.Activity(
            name="I'm back?",
            type=hikari.ActivityType.CUSTOM,
        )
    )


if __name__ == "__main__":
    main()
