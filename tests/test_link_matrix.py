"""The link decision matrix (handoff 01), row by row.

Pure decision logic over existing rows -- no wire, no Discord. Every branch is a
distinct way to mis-attribute someone's scores, so each row gets its own test.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from coda.db.enums import LinkMethod
from coda.db.models import PlayerLink
from coda.players.errors import AlreadyRegistered
from coda.players.service import (
    Linked,
    NeedsApproval,
    ProvenCoexists,
    ProvenOverCode,
    RegistrationService,
)

SVC = RegistrationService()


async def _links(db, account):
    rows = await db.execute(
        select(PlayerLink).where(PlayerLink.arcaea_account_id == account.id)
    )
    return list(rows.scalars())


async def test_first_claim_owns(db, make_account):
    account = await make_account(900000001, "900000001")
    out = await SVC._link(db, 111, account, via=LinkMethod.CODE)
    assert isinstance(out, Linked)
    assert out.link.is_owner is True
    assert out.link.linked_via is LinkMethod.CODE


async def test_same_user_code_raises_already_registered(db, make_account, make_link):
    account = await make_account(900000002, "900000002")
    await make_link(111, account, linked_via=LinkMethod.CODE, is_owner=True)
    with pytest.raises(AlreadyRegistered):
        await SVC._link(db, 111, account, via=LinkMethod.CODE)


async def test_other_user_code_needs_approval_and_creates_no_row(
    db, make_account, make_link
):
    account = await make_account(900000003, "900000003")
    await make_link(111, account, linked_via=LinkMethod.CODE, is_owner=True)

    out = await SVC._link(db, 222, account, via=LinkMethod.CODE)

    assert isinstance(out, NeedsApproval)
    assert out.owner_id == 111
    # No link for 222 was created -- the owner must approve first.
    assert {link.discord_id for link in await _links(db, account)} == {111}


async def test_proven_over_code_promotes_and_demotes(db, make_account, make_link):
    account = await make_account(900000004, "900000004")
    await make_link(111, account, linked_via=LinkMethod.CODE, is_owner=True)

    out = await SVC._link(db, 222, account, via=LinkMethod.ACCOUNT)

    assert isinstance(out, ProvenOverCode)
    assert out.link.is_owner is True
    assert out.link.linked_via is LinkMethod.ACCOUNT
    assert all(link.is_owner is False for link in out.demoted)
    # In the DB: exactly one owner (222), and 111 was demoted.
    by_user = {link.discord_id: link for link in await _links(db, account)}
    assert by_user[111].is_owner is False
    assert by_user[222].is_owner is True


async def test_proven_coexists_leaves_owner_unmoved(db, make_account, make_link):
    account = await make_account(900000005, "900000005")
    await make_link(111, account, linked_via=LinkMethod.ACCOUNT, is_owner=True)

    out = await SVC._link(db, 222, account, via=LinkMethod.ACCOUNT)

    assert isinstance(out, ProvenCoexists)
    assert out.owner_id == 111
    assert out.link.is_owner is False
    by_user = {link.discord_id: link for link in await _links(db, account)}
    assert by_user[111].is_owner is True
    assert by_user[222].is_owner is False
