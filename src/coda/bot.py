"""Bot and lightbulb client construction."""

from __future__ import annotations

import asyncio
import logging

import hikari
import lightbulb

from coda import extensions
from coda.approvals import ApprovalService
from coda.arcaea import client as arcaea_client
from coda.catalog.search import SearchService
from coda.chardle import (
    ChardleChannelService,
    GuessService,
    PuzzleService,
    SessionService,
    StatsService,
)
from coda.config import config
from coda.logging import configure_logging, start_discord, stop_discord
from coda.players import RegistrationService
from coda.players.live import LiveUpdateService
from coda.scores import B30Service, ObservationCache, PollCoordinator, TrackingService
from coda.scores import poller, poster, reconcile
from coda.scores.suppression import PostSuppressor
from coda.settings import ConfigService

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
    client = lightbulb.client_from_app(bot, default_enabled_guilds=config.dev_guild_ids)

    coordinator = PollCoordinator()
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
    registry.register_value(B30Service, B30Service())
    registry.register_value(PuzzleService, PuzzleService())
    registry.register_value(GuessService, GuessService())
    # Holds the per-board FIFO locks, so it must be one instance.
    registry.register_value(SessionService, SessionService())
    registry.register_value(StatsService, StatsService())
    registry.register_value(ChardleChannelService, ChardleChannelService())

    background_tasks: list[asyncio.Task[None]] = []

    @bot.listen(hikari.StartingEvent)
    async def _on_starting(_: hikari.StartingEvent) -> None:
        await client.load_extensions_from_package(extensions)
        await client.start()
        background_tasks.append(
            asyncio.create_task(poller.run(coordinator, observations, bot, posts))
        )
        background_tasks.append(
            asyncio.create_task(poster.run(posts, bot, suppressor))
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
