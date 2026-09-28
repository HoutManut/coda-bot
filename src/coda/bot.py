"""Bot and lightbulb client construction."""

from __future__ import annotations

import asyncio
import logging

import hikari
import lightbulb

from coda import extensions
from coda.approvals import ApprovalService
from coda.arcaea import client as arcaea_client
from coda.catalog import spoilers
from coda.catalog.search import SearchService
from coda.chardle import (
    ChardleChannelService,
    GuessService,
    PuzzleService,
    SessionService,
    StatsService,
)
from coda.config import config
from coda.db.session import async_session
from coda.logging import configure_logging, start_discord, stop_discord
from coda.players import RegistrationService
from coda.players.live import LiveUpdateService
from coda.scores import PotentialService, ObservationCache, PollCoordinator, TrackingService
from coda.scores import poller, poster, reconcile
from coda.scores.suppression import PostSuppressor
from coda.tournaments import cadence as tournament_cadence
from coda.tournaments.board import BoardService
from coda.tournaments.threads import TournamentChannelService
from coda.settings import REGISTRY, ConfigService

logger = logging.getLogger(__name__)


def build() -> hikari.GatewayBot:
    configure_logging()

    # MESSAGE_CONTENT is privileged and must also be enabled in the dev
    # portal. Chardle's reply path reads what the player typed, so without it
    # a reply to a board arrives empty.
    bot = hikari.GatewayBot(
        token=config.bot_token,
        logs=None,
        intents=hikari.Intents.ALL_UNPRIVILEGED | hikari.Intents.MESSAGE_CONTENT,
    )
    # DEV_GUILD_IDS set -> guild-scoped, instant sync, no DM commands (dev).
    # DEV_GUILD_IDS unset -> global, ~1hr propagation, DM-visible (prod).
    # Guild-scoped commands never appear in DMs -- only global ones can.
    client = lightbulb.client_from_app(bot, default_enabled_guilds=config.dev_guild_ids)

    # Seeded with the default; the poll loop pushes the live value every tick.
    coordinator = PollCoordinator(REGISTRY["poll_interval"].default)
    observations = ObservationCache()
    # Written by /recent, read by the poster: both need the same instance, so it
    # is registered for DI *and* handed to the background task, like the cache.
    suppressor = PostSuppressor()
    posts = poster.new_queue()

    registry = client.di.registry_for(lightbulb.di.Contexts.DEFAULT)
    registry.register_value(ConfigService, ConfigService())
    registry.register_value(RegistrationService, RegistrationService())
    registry.register_value(LiveUpdateService, LiveUpdateService())
    registry.register_value(ApprovalService, ApprovalService())
    registry.register_value(SearchService, SearchService())
    registry.register_value(PollCoordinator, coordinator)
    registry.register_value(ObservationCache, observations)
    registry.register_value(PostSuppressor, suppressor)
    registry.register_value(TrackingService, TrackingService())
    registry.register_value(PotentialService, PotentialService())
    registry.register_value(PuzzleService, PuzzleService())
    registry.register_value(GuessService, GuessService())
    # Holds the per-board FIFO locks, so it must be one instance.
    registry.register_value(SessionService, SessionService())
    registry.register_value(StatsService, StatsService())
    registry.register_value(ChardleChannelService, ChardleChannelService())
    registry.register_value(TournamentChannelService, TournamentChannelService())
    # Holds the per-match FIFO locks, so it must be one instance.
    registry.register_value(BoardService, BoardService())

    background_tasks: list[asyncio.Task[None]] = []

    @bot.listen(hikari.StartingEvent)
    async def _on_starting(_: hikari.StartingEvent) -> None:
        # Every render asks whether its chart is spoilered, so the flagged set
        # is cached in-process and reloaded here rather than queried per render.
        async with async_session() as db:
            await spoilers.refresh(db)
        await client.load_extensions_from_package(extensions)
        await client.start()
        background_tasks.append(
            asyncio.create_task(
                poller.run(
                    coordinator, observations, bot, posts,
                    hot=tournament_cadence.hot_keys,
                )
            )
        )
        background_tasks.append(
            asyncio.create_task(poster.run(posts, bot, suppressor, observations))
        )
        background_tasks.append(asyncio.create_task(reconcile.run_reconcile_loop()))
        start_discord(bot)
        logger.info("coda started", extra={"discord": True})

    @bot.listen(hikari.StoppingEvent)
    async def _on_stopping(_: hikari.StoppingEvent) -> None:

        logger.info("coda shutting down", extra={"discord": True})
        await stop_discord()

        for task in background_tasks:
            task.cancel()
        await asyncio.gather(*background_tasks, return_exceptions=True)

        await arcaea_client.close()

    return bot
