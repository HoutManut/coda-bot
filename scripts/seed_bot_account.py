#!/usr/bin/env python
"""Add a bot account to the pool.

Account *creation* stays manual by design -- there is no automated signup path
and none should be built, since it would mean defeating email verification and
CAPTCHA to mass-produce accounts and risking a ban on the hand-made accounts the
bot depends on. This only gets an existing account's credentials into the DB.

    uv run python scripts/seed_bot_account.py --email bot1@example.com
    uv run python scripts/seed_bot_account.py --email bot1@example.com --deactivate
    uv run python scripts/seed_bot_account.py --email bot1@example.com --clear-friends
    uv run python scripts/seed_bot_account.py --list

The password is prompted for rather than taken as an argument, so it stays out
of shell history. The login is exercised before anything is written: a row that
cannot authenticate is worse than no row.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import logging
import sys
from datetime import UTC, datetime

from sqlalchemy import select, update

from coda.arcaea import auth, endpoints, identity
from coda.arcaea.client import close
from coda.arcaea.dto import parse_me
from coda.arcaea.errors import ArcaeaError, InvalidCredentials
from coda.crypto import encrypt
from coda.db.models import ArcaeaAccount, BotAccount
from coda.db.session import async_session, engine

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("seed")


async def _list_accounts() -> int:
    async with async_session() as db:
        rows = await db.execute(select(BotAccount).order_by(BotAccount.id))
        accounts = list(rows.scalars())

    if not accounts:
        print("No bot accounts. Add one with --email.")
        return 0

    print(f"{'id':>3}  {'email':<32} {'active':<7} {'friends':<9} expires")
    for a in accounts:
        expires = a.expires_at.date().isoformat() if a.expires_at else "-"
        print(
            f"{a.id:>3}  {a.email:<32} {str(a.is_active):<7} "
            f"{f'{a.friend_count}/{a.max_friends}':<9} {expires}"
        )
    print("\nfriend counts are stale hints; the pool reads live capacity at add time.")
    return 0


async def _deactivate(email: str) -> int:
    async with async_session() as db:
        row = await db.execute(select(BotAccount).where(BotAccount.email == email))
        account = row.scalar_one_or_none()
        if account is None:
            print(f"No bot account with email {email}.")
            return 1
        account.is_active = False
        await db.commit()
    print(f"Deactivated {email}. The pool will skip it; its friends stay put.")
    return 0


async def _clear_friends(email: str, password: str) -> int:
    """Unfriend everyone on a bot account and free the slots in the DB.

    Live-first, DB-second, same ordering as ``SessionPool.release``: a friend is
    not truly gone until lowiro no longer holds it, so unfriend on the wire, then
    NULL ``bot_account_id`` on the rows that pointed here. Removing by the live
    ``user_id`` (not the DB's view) clears strangers and drift too.
    """
    async with async_session() as db:
        row = await db.execute(select(BotAccount).where(BotAccount.email == email))
        account = row.scalar_one_or_none()
    if account is None:
        print(f"No bot account with email {email}.")
        return 1

    who = identity.coerce(account.browser_identity) or identity.generate()
    print(f"Logging in as {email}...")
    try:
        with identity.bind(who):
            sid, _ = await auth.login(email, password)
            friends = await endpoints.fetch_friends(sid)
            user_ids = [
                f.get("user_id")
                for f in (friends.get("value") or {}).get("friends") or []
                if f.get("user_id") is not None
            ]
            if user_ids:
                print(f"Removing {len(user_ids)} friend(s): {user_ids}")
            for uid in user_ids:
                await endpoints.remove_friend(sid, uid)
    except InvalidCredentials:
        print("Login rejected. Nothing was changed.", file=sys.stderr)
        return 1
    except ArcaeaError as exc:
        print(f"Arcaea API error: {exc}. Some friends may remain.", file=sys.stderr)
        return 1

    # Reconcile the DB even when the live list was empty: the stale friend_count
    # hint and any dangling bot_account_id are exactly the drift this clears.
    async with async_session() as db:
        await db.execute(
            update(ArcaeaAccount)
            .where(ArcaeaAccount.bot_account_id == account.id)
            .values(bot_account_id=None)
        )
        await db.execute(
            update(BotAccount).where(BotAccount.id == account.id).values(friend_count=0)
        )
        await db.commit()

    print(
        f"Cleared {len(user_ids)} live friend(s) from {email}; "
        "DB slots freed and friend_count reset to 0."
    )
    return 0


async def _seed(email: str, password: str) -> int:
    # Decide the browser identity before logging in, so even the very first login
    # goes out as the account's permanent build. Re-seeding keeps the stored one
    # -- a browser does not change overnight; only a fresh row draws a new one.
    async with async_session() as db:
        row = await db.execute(select(BotAccount).where(BotAccount.email == email))
        existing = row.scalar_one_or_none()
    who = identity.coerce(existing.browser_identity) if existing else None
    if who is None:
        who = identity.generate()

    print(f"Logging in as {email}...")
    try:
        with identity.bind(who):
            sid, expires_at = await auth.login(email, password)
            me = parse_me(await endpoints.fetch_me(sid))
            friends = await endpoints.fetch_friends(sid)
    except InvalidCredentials:
        print("Login rejected. Nothing was written.", file=sys.stderr)
        return 1
    except ArcaeaError as exc:
        print(f"Arcaea API error: {exc}. Nothing was written.", file=sys.stderr)
        return 1

    friend_count = len((friends.get("value") or {}).get("friends") or [])
    now = datetime.now(UTC)

    # A bot account must not also be a tracked player. If this arc_user_id is
    # already a player account, seeding it as pool infrastructure would let the
    # poller track and stray our own bot -- the reverse of the /register bot-code
    # refusal. Refuse; unregister the player link first if this really is a bot.
    async with async_session() as db:
        clash = await db.execute(
            select(ArcaeaAccount.id).where(ArcaeaAccount.arc_user_id == me.arc_user_id)
        )
        if clash.scalar_one_or_none() is not None:
            print(
                f"{me.friend_code} is already registered as a tracked player "
                "account. Not seeding it as a bot -- unregister that player first.",
                file=sys.stderr,
            )
            return 1

    async with async_session() as db:
        row = await db.execute(select(BotAccount).where(BotAccount.email == email))
        account = row.scalar_one_or_none()

        if account is None:
            account = BotAccount(email=email)
            db.add(account)
            action = "Added"
        else:
            # Re-seeding is how a password change or a deactivated account gets
            # fixed, so this must update rather than refuse.
            action = "Updated"

        account.browser_identity = dict(who)
        account.password_enc = encrypt(password)
        # Stored so /register can refuse someone registering a bot as a player.
        account.friend_code = me.friend_code or None
        account.cookie_data = {"sid": sid}
        account.expires_at = expires_at
        account.last_login_at = now
        account.last_refreshed_at = now
        account.friend_count = friend_count
        account.max_friends = me.max_friends
        account.is_active = True
        await db.commit()
        account_id = account.id

    print(
        f"\n{action} bot account #{account_id}\n"
        f"  in-game name : {me.name} (user_id {me.arc_user_id})\n"
        f"  friend code  : {me.friend_code}\n"
        f"  capacity     : {friend_count}/{me.max_friends} friends used\n"
        f"  browser      : {who['sec_ch_ua_platform']} / {who['user_agent'].split(') ', 1)[-1]}\n"
        f"  session until: {expires_at.date()}"
    )
    return 0


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", help="the bot account's lowiro email")
    parser.add_argument("--list", action="store_true", help="list bot accounts and exit")
    parser.add_argument(
        "--deactivate", action="store_true", help="deactivate --email instead of adding it"
    )
    parser.add_argument(
        "--clear-friends",
        action="store_true",
        help="unfriend everyone on --email and free the slots in the DB",
    )
    args = parser.parse_args()

    try:
        if args.list:
            return await _list_accounts()
        if not args.email:
            parser.error("--email is required (or use --list)")
        if args.deactivate:
            return await _deactivate(args.email)
        password = getpass.getpass(f"Password for {args.email}: ")
        if args.clear_friends:
            if not password:
                print("No password given.", file=sys.stderr)
                return 1
            return await _clear_friends(args.email, password)
        if not password:
            print("No password given.", file=sys.stderr)
            return 1
        return await _seed(args.email, password)
    finally:
        await close()
        await engine.dispose()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
