"""Registration: Discord user -> Arcaea account, by friend code or credentials.

The friend path and the own (credentials) path are ORTHOGONAL, not alternatives.
A player may end up with neither, either, or both:

    bot_account_id set -> friend path  (batched, score-only)
    PlayerCredential   -> own path     (per-user, full detail)

Which is why adding credentials to an account you already friend-linked is an
in-place upgrade of the one link (not a second link), and ``/unlink`` is a plain
DELETE of the credential that leaves the friend link tracking at tier 1.

One account per Discord user, and no switching. A user holds exactly one
``PlayerLink`` (``UniqueConstraint("discord_id")``); registering a *different*
account while linked is refused (``AlreadyLinkedElsewhere``) before any friend
slot is consumed. Changing accounts means ``/unregister`` first -- that deletes
the link and, if it was the account's last, *strays* the account: its friend
slot is released and polling paused, but the row and its ``play_scores`` are
kept, because there is no score backfill and dropping history is irreversible.
The reverse cardinality (many Discord users -> one account) stays legal, created
by the consent flow when someone proves an account another user code-linked.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from coda.arcaea import auth, endpoints, identity
from coda.arcaea.dto import Friend, Me, parse_friends, parse_me
from coda.arcaea.errors import AlreadyFriend, ApiError, PlayerNotFound
from coda.crypto import encrypt
from coda.db.enums import LinkMethod
from coda.db.models import ArcaeaAccount, PlayerCredential, PlayerLink
from coda.players import reserved
from coda.players.errors import (
    AlreadyLinkedElsewhere,
    AlreadyRegistered,
    AmbiguousFriend,
    PlayerUnreachable,
    ReservedCodeError,
)
from coda.sessions import BotSession, SessionPool
from coda.utils.friend_code import clean_friend_code

logger = logging.getLogger(__name__)

# How many bot accounts to try before giving up when adds keep getting rejected.
# Covers the last-slot placement race (see _place_and_add); small on purpose --
# with <50 users a real collision clears in one retry, and a higher ceiling just
# means burning more accounts on a genuinely broken one.
_MAX_PLACEMENT_ATTEMPTS = 3


@dataclass(frozen=True, slots=True)
class Registration:
    """The outcome of a registration, with what we already learned in passing.

    ``rating`` comes free: the add_friend response (or /me) already carries it,
    so surfacing it costs no extra request. None means the player hides their
    PTT in-game, or we simply could not see it -- never "zero".
    """

    account: ArcaeaAccount
    rating: float | None
    display_name: str | None


# -- link outcomes ------------------------------------------------------------
#
# ``_link`` returns one of these instead of a bare row: linking is a decision
# over who already holds the account, not an unconditional INSERT. The public
# register_* methods map ``Linked`` to a ``Registration`` and surface the rest so
# the extension can gate, promote, or notify. See handoff 01's matrix.


@dataclass(frozen=True, slots=True)
class Linked:
    """First/only claim, or a proven coexisting link -- the row was created."""

    link: PlayerLink


@dataclass(frozen=True, slots=True)
class NeedsApproval:
    """An unproven code claim on an account someone else owns.

    No row was created. The owner must approve before a link exists (handoff 02);
    this is what ``AccountClaimed`` used to refuse outright.
    """

    owner_id: int
    account: ArcaeaAccount


@dataclass(frozen=True, slots=True)
class ProvenOverCode:
    """A login proved an account that until now was only code-linked.

    The proven user is the new owner; the prior code-linkers are demoted and
    offered removal (owner's call, at the time). The credential is stored.
    """

    account: ArcaeaAccount
    link: PlayerLink
    demoted: list[PlayerLink]


@dataclass(frozen=True, slots=True)
class ProvenCoexists:
    """A second proven login on an account that already had a proven owner.

    Both links coexist; ownership does not move. The first owner is notified but
    does not gate -- both hold the password.
    """

    account: ArcaeaAccount
    owner_id: int
    link: PlayerLink


LinkOutcome = Linked | NeedsApproval | ProvenOverCode | ProvenCoexists


# -- unregister outcomes ------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Strayed:
    """The user's link was the account's last -- the account was strayed.

    Its friend slot was released and polling paused, but the row and its
    ``play_scores`` are kept. Relinking the same code reattaches the history.
    """

    account: ArcaeaAccount


@dataclass(frozen=True, slots=True)
class LeftShared:
    """The user left a shared account; other links remain, so it stays active."""

    account: ArcaeaAccount


@dataclass(frozen=True, slots=True)
class NotLinked:
    """There was no link to remove."""


UnregisterOutcome = Strayed | LeftShared | NotLinked


class RegistrationService:
    """Stateless; takes the session per call, like ConfigService."""

    async def register_by_code(
        self, db: AsyncSession, discord_id: int, raw_code: str
    ) -> Registration | NeedsApproval:
        """Link a Discord user to an Arcaea account by friend code.

        Returns a ``Registration`` on success, or ``NeedsApproval`` when the
        account is already owned by someone else -- an unproven code claim can no
        longer overwrite it, but the caller may ask the owner (handoff 02).

        Raises InvalidFriendCode (bad shape, no network call), PlayerUnreachable
        (401), AmbiguousFriend (602 recovery failed), NoCapacity,
        AlreadyRegistered, or AlreadyLinkedElsewhere (already linked to a
        different account -- no switching).
        """
        # Locally first: lowiro accepts garbage and answers 401, which is
        # indistinguishable from a real typo. This is what buys a good message.
        code = clean_friend_code(raw_code)
        logger.info("register_by_code: discord=%s code=%s", discord_id, code)

        # Well-formed but off-limits. Same reasoning as the shape check: decide
        # here, because lowiro's answer would tell the user nothing useful.
        # Before any network call.
        entry = reserved.check_static(code, discord_id)
        if entry is not None:
            raise ReservedCodeError(entry.reason, entry.message)

        # Our own bot accounts are refused honestly -- "you can't use that code" --
        # not with a fake not-found. The old oracle-shrouding (same error + mimicked
        # latency as an unknown code) was dropped: the repo is open source, so a lie
        # fools nobody and a real user is left told their code does not exist. See
        # reserved.is_bot_account.
        if await reserved.is_bot_account(db, code):
            raise ReservedCodeError("bot_account", "You can't use that friend code.")

        # No switching: if they already link a DIFFERENT account, refuse here --
        # before _acquire, so a switch the user can't make never friends anyone
        # or burns a pool slot. Same code = fall through (re-register is caught as
        # AlreadyRegistered in _link). One query, no API call.
        current = await self.current_account(db, discord_id)
        if current is not None and current.friend_code != code:
            raise AlreadyLinkedElsewhere(current.friend_code, current.display_name)

        account = await self._find_by_code(db, code)
        friend: Friend | None = None
        if account is None:
            account, friend = await self._acquire(db, code)
        elif account.bot_account_id is None:
            # Known but STRAYED (unregistered earlier): the row + its history were
            # kept, but its friend slot was released. Link-only would leave it
            # unfriended and inactive -- invisible to the poller -- so re-place it
            # on a bot and reactivate, reattaching the preserved play_scores.
            friend = await self._reacquire(db, account)
        else:
            # Zero API calls. This fast path is also what makes a 602 below a
            # genuine drift signal rather than the normal path.
            logger.info("register_by_code: %s already known, linking only", code)

        outcome = await self._link(db, discord_id, account, via=LinkMethod.CODE)
        if isinstance(outcome, NeedsApproval):
            # No link row was created; the owner must approve first. Nothing to
            # commit -- an unowned account never reaches here (it has no existing
            # links, so it links straight through), so no _acquire is left dangling.
            return outcome
        await db.commit()
        return Registration(
            account=account,
            rating=friend.rating if friend else None,
            display_name=account.display_name,
        )

    async def register_by_credentials(
        self, db: AsyncSession, discord_id: int, email: str, password: str
    ) -> Registration | ProvenOverCode | ProvenCoexists:
        """Link by the player's own lowiro login.

        Needs no friend code and no friend slot: /webapi/user/me returns both
        the account's user_id and its own user_code, so the credentials identify
        the player by themselves.

        Logging in as an account you already code-linked *upgrades* that one link
        in place (the tier fix); logging in as a *different* account than the one
        you link raises AlreadyLinkedElsewhere (no switching).

        Raises InvalidCredentials (403, terminal) if the login is rejected.
        """
        logger.info("register_by_credentials: discord=%s", discord_id)

        # Our own bot accounts are off-limits on THIS path too, not just the code
        # path: a bot account is pool infrastructure, and linking one as a player
        # would let it be tracked/strayed like a person. Bot accounts are keyed by
        # their unique email, so refuse BEFORE spending a login -- no round trip,
        # and this catches rows seeded before friend_code existed. Basic refusal,
        # worded for this path.
        if await reserved.is_bot_email(db, email):
            raise ReservedCodeError("bot_account", "You can't use that account.")

        # Give this own-path session a fixed, coherent browser identity and use
        # it from the very first login, so the registration request and every
        # later poll go out as the same build. A fresh one per registration is
        # fine here (unlike a bot account): a person re-authenticating from a new
        # browser is ordinary, so overwriting on re-register still looks real.
        who = identity.generate()
        # Validating by logging in is not an extra round trip we could skip --
        # we need /me's user_id to know who this even is.
        with identity.bind(who):
            sid, expires_at = await auth.login(email, password)
            me = parse_me(await endpoints.fetch_me(sid))

        # No switching: if they already link a DIFFERENT account, refuse. The
        # login already happened, but no friend/slot was consumed. Compare on
        # arc_user_id so we never create the new account row just to roll it back.
        current = await self.current_account(db, discord_id)
        if current is not None and current.arc_user_id != me.arc_user_id:
            raise AlreadyLinkedElsewhere(current.friend_code, current.display_name)

        account = await self._find_by_arc_user_id(db, me.arc_user_id)
        if account is None:
            account = ArcaeaAccount(
                arc_user_id=me.arc_user_id,
                friend_code=me.friend_code,
                display_name=me.name,
                # No bot account holds them. The friend path is simply
                # unavailable; the own path does not need it.
                bot_account_id=None,
            )
            db.add(account)
            await db.flush()
            logger.info("register_by_credentials: created account %s", me.arc_user_id)
        else:
            # Refresh what /me just told us, but leave bot_account_id ALONE:
            # if a bot already friends them, that link keeps its free batching.
            account.display_name = me.name
            account.friend_code = me.friend_code

        # via=ACCOUNT: we just logged in as this account, the only ownership proof
        # the friend-code path can never provide. This may promote us over prior
        # code-linkers or coexist with another proven owner -- see _link.
        outcome = await self._link(db, discord_id, account, via=LinkMethod.ACCOUNT)
        await self._store_credential(
            db, account, email, password, sid, expires_at, me, who
        )
        await db.commit()
        if isinstance(outcome, Linked):
            return Registration(account=account, rating=me.rating, display_name=me.name)
        # ProvenOverCode / ProvenCoexists: the extension shows the same success but
        # also offers removal / notifies the other owner.
        return outcome

    async def unlink_credentials(self, db: AsyncSession, discord_id: int) -> bool:
        """Delete a user's stored credentials. Returns False if there were none.

        The friend link is untouched, so scores keep flowing at tier 1.
        """
        row = await db.execute(
            select(PlayerCredential)
            .join(PlayerLink, PlayerLink.arcaea_account_id == PlayerCredential.arcaea_account_id)
            .where(PlayerLink.discord_id == discord_id)
        )
        credential = row.scalar_one_or_none()
        if credential is None:
            return False
        await db.delete(credential)
        await db.commit()
        logger.info("unlink_credentials: removed for discord=%s", discord_id)
        return True

    async def unregister(
        self, db: AsyncSession, discord_id: int
    ) -> UnregisterOutcome:
        """Remove this user's link. If it was the account's last, stray it.

        Deletes the caller's own ``PlayerLink``. When other links remain (a
        shared account), the account stays active -- ``LeftShared``. When it was
        the last, the account is strayed (slot released, sync paused, credential
        deleted, row + play_scores KEPT) -- ``Strayed``. ``NotLinked`` if there
        was nothing to remove.
        """
        row = await db.execute(
            select(PlayerLink).where(PlayerLink.discord_id == discord_id)
        )
        link = row.scalar_one_or_none()
        if link is None:
            return NotLinked()

        account = await db.get(ArcaeaAccount, link.arcaea_account_id)
        assert account is not None  # FK guarantees the row exists
        await db.delete(link)
        await db.flush()

        remaining = await db.execute(
            select(PlayerLink.id)
            .where(PlayerLink.arcaea_account_id == account.id)
            .limit(1)
        )
        if remaining.scalar_one_or_none() is not None:
            await db.commit()
            logger.info(
                "unregister: discord=%s left shared account %s",
                discord_id,
                account.friend_code,
            )
            return LeftShared(account=account)

        await self._stray(db, account)
        await db.commit()
        return Strayed(account=account)

    # -- internals -------------------------------------------------------

    async def _stray(self, db: AsyncSession, account: ArcaeaAccount) -> None:
        """The account lost its last link: free its slot and pause sync, but KEEP
        the row and its play_scores.

        The friend/free-own tiers have no score backfill, so history dropped here
        is gone forever, while the only *private* stored item -- the credential --
        is deleted. Relinking the same code later re-acquires a slot and reattaches
        the preserved history (``_find_by_code`` finds the same row).
        """
        # Give back the friend slot first; release() unfriends then NULLs
        # bot_account_id, and never raises on a failed unfriend.
        await SessionPool(db).release(account)
        account.is_active = False

        row = await db.execute(
            select(PlayerCredential).where(
                PlayerCredential.arcaea_account_id == account.id
            )
        )
        credential = row.scalar_one_or_none()
        if credential is not None:
            await db.delete(credential)

        logger.info(
            "unregister: strayed account %s (slot freed, sync paused, credential "
            "cleared, history kept)",
            account.friend_code,
        )

    async def _find_by_code(self, db: AsyncSession, code: str) -> ArcaeaAccount | None:
        row = await db.execute(
            select(ArcaeaAccount).where(ArcaeaAccount.friend_code == code)
        )
        return row.scalar_one_or_none()

    async def _find_by_arc_user_id(
        self, db: AsyncSession, arc_user_id: int
    ) -> ArcaeaAccount | None:
        row = await db.execute(
            select(ArcaeaAccount).where(ArcaeaAccount.arc_user_id == arc_user_id)
        )
        return row.scalar_one_or_none()

    async def current_account(
        self, db: AsyncSession, discord_id: int
    ) -> ArcaeaAccount | None:
        """The one account this Discord user links, or None.

        unique(discord_id) guarantees at most one. Drives the no-switching
        refusal in both register paths, and the ``/unregister`` confirm UI.
        """
        row = await db.execute(
            select(ArcaeaAccount)
            .join(PlayerLink, PlayerLink.arcaea_account_id == ArcaeaAccount.id)
            .where(PlayerLink.discord_id == discord_id)
        )
        return row.scalar_one_or_none()

    async def _acquire(
        self, db: AsyncSession, code: str
    ) -> tuple[ArcaeaAccount, Friend]:
        """Friend the player from a bot account and record who they turned out to be.

        Returns the Friend as well: it carries their name and PTT, which the
        add response already gave us, so the caller needs no extra request.
        """
        pool = SessionPool(db)
        session, candidates = await self._place_and_add(pool, code)
        friend = self._exactly_one(candidates, code)
        account = ArcaeaAccount(
            arc_user_id=friend.arc_user_id,
            friend_code=code,
            display_name=friend.name or None,
            bot_account_id=session.account_id,
        )
        db.add(account)
        await db.flush()
        logger.info(
            "register: %s is arc_user_id %s (%s) on bot account %s",
            code,
            friend.arc_user_id,
            friend.name,
            session.account_id,
        )
        return account, friend

    async def _reacquire(self, db: AsyncSession, account: ArcaeaAccount) -> Friend:
        """Re-friend a strayed account onto a bot and reactivate it in place.

        Updates the existing row rather than creating a new one (``_acquire``
        would collide on the unique arc_user_id/friend_code), so the preserved
        play_scores stay attached. Self-heals a failed-unfriend drift: if lowiro
        still holds the friend, ``_place_and_add`` recovers via AlreadyFriend.
        """
        pool = SessionPool(db)
        session, candidates = await self._place_and_add(pool, account.friend_code)
        friend = self._exactly_one(candidates, account.friend_code)
        account.bot_account_id = session.account_id
        account.is_active = True
        await db.flush()
        logger.info(
            "register: re-acquired strayed %s on bot account %s",
            account.friend_code,
            session.account_id,
        )
        return friend

    async def _place_and_add(
        self, pool: SessionPool, code: str
    ) -> tuple[BotSession, list[Friend]]:
        """Place the code on a bot account and friend it, retrying past a collision.

        The last-slot race (pool.place): two concurrent registrations can both
        see the same free slot, and the loser's add is rejected with an unmapped
        error_code -> ApiError. That rejection is a *definite* server response, so
        the add did NOT take effect -- unlike a TransportError (no response,
        ambiguous outcome), it is safe to retry on another account without risk of
        a double-friend. So we catch ApiError only, exclude that account, and
        re-place; TransportError propagates untouched. Bounded + logged so a
        genuinely broken account can't silently burn the whole pool.
        """
        exclude: set[int] = set()
        last_error: ApiError | None = None
        for _ in range(_MAX_PLACEMENT_ATTEMPTS):
            session, known = await pool.place(code, exclude=exclude)
            try:
                body = await session.call(endpoints.add_friend, code)
                return session, endpoints.unknown_friends(body, known)
            except PlayerNotFound:
                # A PLAYER error. Do not flag the account, do not try the next one:
                # every account returns 401 for the same nonexistent code.
                logger.info("register: lowiro does not know friend code %s", code)
                raise PlayerUnreachable(code) from None
            except AlreadyFriend:
                # The error body carries no friends list, so re-read and diff.
                # Reaching here means our rows drifted from lowiro's reality.
                logger.warning(
                    "register: %s already friended by bot account %s but we had no "
                    "row -- drift; recovering by diff",
                    code,
                    session.account_id,
                )
                return session, await self._diff_live_friends(session, known)
            except ApiError as exc:
                # Definite server rejection -- likely the last-slot collision.
                # Exclude this account and try the next; the add did not land.
                logger.warning(
                    "register: add %s on bot account %s rejected (error_code %s); "
                    "excluding and retrying next account",
                    code,
                    session.account_id,
                    exc.error_code,
                )
                exclude.add(session.account_id)
                last_error = exc

        # Exhausted attempts: surface the real rejection, not a silent NoCapacity.
        assert last_error is not None
        raise last_error

    async def _diff_live_friends(
        self, session: BotSession, known: set[int]
    ) -> list[Friend]:
        friends = parse_friends(await session.call(endpoints.fetch_friends))
        return [f for f in friends if f.arc_user_id not in known]

    def _exactly_one(self, candidates: list[Friend], code: str) -> Friend:
        """Resolve the diff to one friend, or refuse.

        Ambiguity here would mis-attribute a stranger's scores to a Discord
        user, so this never guesses -- it raises and a human reconciles.
        """
        if len(candidates) == 1:
            return candidates[0]
        logger.error(
            "register: cannot identify %s -- diff yielded %d candidates (%s). "
            "Needs manual reconcile; refusing to guess",
            code,
            len(candidates),
            sorted(f.arc_user_id for f in candidates),
        )
        raise AmbiguousFriend(code)

    async def _link(
        self,
        db: AsyncSession,
        discord_id: int,
        account: ArcaeaAccount,
        *,
        via: LinkMethod,
    ) -> LinkOutcome:
        """Decide and (usually) create the link. See handoff 01's matrix.

        ``via`` is how the caller arrived: ACCOUNT is proven ownership (they
        logged in), CODE is an unproven claim on a public friend code. The return
        tells the caller what happened -- a link was created, or the owner must be
        asked (CODE onto an owned account), or ownership just moved (ACCOUNT over
        code-linkers), or two proven owners now coexist.
        """
        rows = await db.execute(
            select(PlayerLink).where(PlayerLink.arcaea_account_id == account.id)
        )
        existing = list(rows.scalars())

        # This Discord user already holds this account. Re-registering the same
        # code is a no-op error; logging in as it is the tier upgrade -- keep the
        # one link (unique(discord_id) forbids a second) and flip it to proven.
        own = next((link for link in existing if link.discord_id == discord_id), None)
        if own is not None:
            if via is LinkMethod.CODE:
                raise AlreadyRegistered(account.friend_code)
            return await self._prove_in_place(db, own, existing)

        # First to claim it owns it, by whichever method brought them.
        if not existing:
            link = PlayerLink(
                discord_id=discord_id,
                arcaea_account_id=account.id,
                linked_via=via,
                is_owner=True,
            )
            db.add(link)
            return Linked(link)

        owner = self._owner_link(existing)

        # An unproven code claim on an account someone else owns: create nothing,
        # ask the owner. A public code proves nothing, so we no longer refuse
        # outright (old AccountClaimed) nor allow -- we defer to the one person
        # who can tell an alt from a stranger.
        if via is LinkMethod.CODE:
            return NeedsApproval(owner_id=owner.discord_id, account=account)

        # via is ACCOUNT -- proven ownership.
        if owner.linked_via is LinkMethod.ACCOUNT:
            # Someone already proved it. Coexist; ownership does not move.
            link = PlayerLink(
                discord_id=discord_id,
                arcaea_account_id=account.id,
                linked_via=LinkMethod.ACCOUNT,
                is_owner=False,
            )
            db.add(link)
            return ProvenCoexists(
                account=account, owner_id=owner.discord_id, link=link
            )

        # Everyone here linked by code; this login is the first proof. Promote the
        # proven user, demote the code-linkers. Flush the demotions BEFORE the
        # insert so the partial unique index (one is_owner per account) never sees
        # two owners at once.
        for link in existing:
            link.is_owner = False
        await db.flush()
        link = PlayerLink(
            discord_id=discord_id,
            arcaea_account_id=account.id,
            linked_via=LinkMethod.ACCOUNT,
            is_owner=True,
        )
        db.add(link)
        return ProvenOverCode(account=account, link=link, demoted=existing)

    async def _prove_in_place(
        self, db: AsyncSession, own: PlayerLink, existing: list[PlayerLink]
    ) -> LinkOutcome:
        """Upgrade the caller's own existing link to proven (they just logged in).

        The tier fix: adding credentials to an account you code-linked keeps the
        one link and flips it to ACCOUNT. It seizes ownership unless another
        *proven* owner already holds the account, in which case it coexists and
        ownership does not move. Idempotent when the link is already proven.
        """
        if own.linked_via is LinkMethod.ACCOUNT:
            # Re-login on an already-proven link; the credential refresh in the
            # caller does the useful work. Ownership unchanged.
            return Linked(own)

        own.linked_via = LinkMethod.ACCOUNT
        other_owner = next(
            (link for link in existing if link.is_owner and link.id != own.id), None
        )
        if other_owner is not None and other_owner.linked_via is LinkMethod.ACCOUNT:
            # A proven owner already exists -- coexist, don't seize ownership.
            return Linked(own)

        # No owner, or only an unproven code-owner: proof wins ownership. Clear
        # the old owner first so the partial unique index never sees two.
        if other_owner is not None:
            other_owner.is_owner = False
            await db.flush()
        own.is_owner = True
        return Linked(own)

    def _owner_link(self, links: list[PlayerLink]) -> PlayerLink:
        """The link that speaks for the account. Backfill guarantees one, but
        fall back to the oldest rather than trust it -- a missing owner must never
        raise here."""
        for link in links:
            if link.is_owner:
                return link
        return min(links, key=lambda link: (link.linked_at, link.id))

    async def _store_credential(
        self,
        db: AsyncSession,
        account: ArcaeaAccount,
        email: str,
        password: str,
        sid: str,
        expires_at: datetime,
        me: Me,
        who: identity.BrowserIdentity,
    ) -> None:
        row = await db.execute(
            select(PlayerCredential).where(
                PlayerCredential.arcaea_account_id == account.id
            )
        )
        credential = row.scalar_one_or_none()
        now = datetime.now(UTC)
        # Refreshed on every /me: compared against now() at read time, so a
        # lapsed subscription needs no user action and raises no API error.
        expire_ts = me.arcaea_online_expire_ts

        if credential is None:
            db.add(
                PlayerCredential(
                    arcaea_account_id=account.id,
                    email_enc=encrypt(email),
                    password_enc=encrypt(password),
                    browser_identity=dict(who),
                    cookie_data={"sid": sid},
                    expires_at=expires_at,
                    arcaea_online_expire_ts=expire_ts,
                    last_login_at=now,
                    is_valid=True,
                )
            )
        else:
            credential.email_enc = encrypt(email)
            credential.password_enc = encrypt(password)
            credential.browser_identity = dict(who)
            credential.cookie_data = {"sid": sid}
            credential.expires_at = expires_at
            credential.arcaea_online_expire_ts = expire_ts
            credential.last_login_at = now
            credential.is_valid = True
