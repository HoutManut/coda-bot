"""Arcaea players, their Discord links, and their optional own-account credentials.

``bot_account_id`` and ``PlayerCredential`` are ORTHOGONAL, not two branches of
one choice (``arcaea-api-layer.md`` §9). A player may have neither, either, or
both:

    bot_account_id set -> friend path available   (batched, score-only)
    PlayerCredential   -> own path available      (per-user, full detail)

The read path is chosen per query, not per user. This is what dissolves
promote/demote into a plain INSERT/DELETE of a credential row, leaving the
friend link untouched -- no acquire-before-release ordering, no leaked slots.

Tier is DERIVED from these rows, never stored: a stored tier enum goes stale
silently the moment a subscription lapses, with no user action and no API error.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from coda.db.base import Base
from coda.db.enums import LinkMethod, link_method_type


class ArcaeaAccount(Base):
    """One row per in-game player, whether or not any Discord user claims them."""

    __tablename__ = "arcaea_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # The in-game user_id. Can be very small (a real account has user_id 4) --
    # never assume a 7-digit width or left-pad it.
    arc_user_id: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    # Always 9 digits; validated locally before any request, because lowiro does
    # not validate shape and answers 401 to garbage exactly as to a real typo.
    friend_code: Mapped[str] = mapped_column(String(9), nullable=False, unique=True)
    display_name: Mapped[str | None] = mapped_column(String)

    # Which bot account has them friended. NULL = nobody does, so the friend
    # path is unavailable for them. This column is read in sessions/pool.py and
    # nowhere else -- it must never reach a service signature or a ScoreResult.
    bot_account_id: Mapped[int | None] = mapped_column(ForeignKey("bot_accounts.id"))

    # False = strayed: the account lost its last PlayerLink, so its friend slot
    # was released and polling is paused, but the row and its play_scores are
    # kept (there is no score backfill, so dropping history is irreversible).
    # Relinking the same code flips this back on and re-acquires a slot. Distinct
    # from BotAccount.is_active. Written/read by unregister + the poller.
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    # False = the owner opted out of RECORDING plays. Fetching is unaffected --
    # an on-demand /recent still reads the wire and renders what it saw; the
    # play just never reaches play_scores. Distinct from is_active (strayed, a
    # link-state fact) and from LiveUpdatePref.enabled (where updates post, a
    # per-Discord-user preference): this one is per ACCOUNT, so only the link
    # with is_owner may change it. Enforced in scores/service.py::ingest.
    tracking_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    linked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class PlayerLink(Base):
    """Discord user <-> Arcaea account.

    One account per Discord user (``UniqueConstraint("discord_id")``): a user
    holds exactly one link. There is no switching -- registering a *different*
    account while linked is refused (``AlreadyLinkedElsewhere``); changing
    accounts means ``/unregister`` first, which strays the old one.

    The reverse is legal: many Discord users -> one account, created by the
    consent flow in ``players/`` when someone proves ownership of an account
    another user code-linked.
    """

    __tablename__ = "player_links"
    __table_args__ = (
        UniqueConstraint("discord_id"),
        # At most one owner per account -- the single link that speaks for it.
        # DB-enforced rather than by convention: a split owner would silently
        # mis-attribute whose scores are whose.
        Index(
            "uq_player_links_owner",
            "arcaea_account_id",
            unique=True,
            postgresql_where=text("is_owner"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    discord_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    arcaea_account_id: Mapped[int] = mapped_column(
        ForeignKey("arcaea_accounts.id", ondelete="CASCADE"), nullable=False
    )
    # How this link was established: 'account' is proven (the user logged in),
    # 'code' is an unproven claim on a public friend code. Drives the consent
    # matrix in players/service.py.
    linked_via: Mapped[LinkMethod] = mapped_column(
        link_method_type, nullable=False, server_default=LinkMethod.CODE.value
    )
    # Who speaks for the account (per-account ownership) when many Discord users
    # share it. At most one true per account, via the partial unique index above.
    is_owner: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    linked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class PlayerCredential(Base):
    """A player's own lowiro login, opted in for richer per-play data.

    Entirely optional. Its presence unlocks note counts, health, clear_type and
    modifier -- fields the friend endpoint never returns for anyone, which is a
    property of the endpoint rather than of the user, so there is no way to get
    them without this.
    """

    __tablename__ = "player_credentials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    arcaea_account_id: Mapped[int] = mapped_column(
        ForeignKey("arcaea_accounts.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    email_enc: Mapped[str] = mapped_column(String, nullable=False)
    password_enc: Mapped[str] = mapped_column(String, nullable=False)

    # One fixed, self-consistent Chrome header set this player's own-path session
    # impersonates for its whole life -- same contract and rationale as
    # BotAccount.browser_identity (see coda.arcaea.identity). Generated when the
    # credential is created; nullable so a pre-existing row falls back to the
    # default identity until re-seeded.
    browser_identity: Mapped[dict | None] = mapped_column(JSONB)

    # Same contract as BotAccount: {"sid": ...} verbatim, 203 is the truth.
    cookie_data: Mapped[dict | None] = mapped_column(JSONB)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Tier-3 discriminator: 0 = no Arcaea Online subscription. Refresh on every
    # /me. Compared against now() at read time so a lapsed sub is a non-event.
    arcaea_online_expire_ts: Mapped[int | None] = mapped_column(BigInteger)

    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # False = login returned 403. Terminal; never retried.
    is_valid: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    linked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
