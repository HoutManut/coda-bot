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
from coda.config import config
from coda.logging import configure_logging, start_discord, stop_discord
from coda.players import RegistrationService
from coda.players.live import LiveUpdateService
from coda.scores import ObservationCache, PollCoordinator, TrackingService
from coda.scores import poller, reconcile
from coda.settings import ConfigService

logger = logging.getLogger(__name__)


def build() -> hikari.GatewayBot:
    configure_logging()

    bot = hikari.GatewayBot(token=config.bot_token, logs=None)
    client = lightbulb.client_from_app(bot, default_enabled_guilds=config.dev_guild_ids)

    coordinator = PollCoordinator()
    observations = ObservationCache()

    registry = client.di.registry_for(lightbulb.di.Contexts.DEFAULT)
    registry.register_value(ConfigService, ConfigService())
    registry.register_value(RegistrationService, RegistrationService())
    registry.register_value(LiveUpdateService, LiveUpdateService())
    registry.register_value(ApprovalService, ApprovalService())
    registry.register_value(SearchService, SearchService())
    registry.register_value(PollCoordinator, coordinator)
    registry.register_value(ObservationCache, observations)
    registry.register_value(TrackingService, TrackingService())

    background_tasks: list[asyncio.Task[None]] = []

    @bot.listen(hikari.StartingEvent)
    async def _on_starting(_: hikari.StartingEvent) -> None:
        await client.load_extensions_from_package(extensions)
        await client.start()
        background_tasks.append(
            asyncio.create_task(poller.run(coordinator, observations, bot))
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
