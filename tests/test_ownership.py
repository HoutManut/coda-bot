"""What a declaration covers, and what a tick writes.

Two things here regress silently. The first is the predicate pair: a pack tick
grants a narrower set than it clears, and if the counter behind the checkmark
ever disagrees with the writer, a pack can never read as fully owned and the
picker looks broken with no error anywhere. The second is scope -- a menu
reports only its own chunk, so a write that reaches outside it silently deletes
answers the player never saw.

Beyond is the reason both matter: it is cleared with its pack but never granted
by one, which is exactly the asymmetry a naive symmetric write would lose.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from coda.db.enums import DifficultyClass
from coda.db.models import PlayScore, Song, SongDifficulty
from coda.ownership.picker import (
    EXCLUDED_PACK_IDS,
    Option,
    beyond_options,
    chunked,
    held_count,
    locked_note,
    pack_options,
    pickable,
    range_label,
)
from coda.ownership.service import (
    FREE_PACK_IDS,
    beyond_charts,
    inferred_pack_ids,
    charts_in_packs,
    charts_in_song,
    clear_all,
    declared_chart_ids,
    pack_counts,
    playable_chart_ids,
    replace,
)

# A small real pack: 9 songs, two of them carrying a Beyond.
PACK = "core"


async def _account(make_account, code: str):
    return await make_account(int(code), code)


async def _a_beyond_of(db: AsyncSession, account_id: int, pack_id: str) -> int:
    """One offered Beyond from a named pack -- the offer also carries the free
    pack's 20, which belong to no pack under test."""
    for entry in await beyond_charts(db, account_id):
        if entry.song.pack_id == pack_id:
            return entry.chart.id
    raise AssertionError(f"{pack_id} offered no Beyond")


# --- the predicate pair -----------------------------------------------------


async def test_pack_tick_grants_no_beyond(db: AsyncSession):
    granted = await charts_in_packs(db, {PACK})
    beyond = await db.scalars(
        select(SongDifficulty.id)
        .join(Song, Song.song_id == SongDifficulty.song_id)
        .where(
            Song.pack_id == PACK,
            SongDifficulty.difficulty.in_(
                [DifficultyClass.BYD, DifficultyClass.BYD_2]
            ),
        )
    )
    assert set(beyond), "core must have a Beyond for this test to mean anything"
    assert granted.isdisjoint(set(beyond))


async def test_untick_scope_covers_beyond(db: AsyncSession):
    """What a tick clears is strictly wider than what it grants."""
    granted = await charts_in_packs(db, {PACK})
    clearable = await charts_in_packs(db, {PACK}, include_beyond=True)
    assert granted < clearable


async def test_checkmark_counts_exactly_what_a_tick_writes(
    db: AsyncSession, make_account
):
    """The invariant: writer and counter share one predicate, so a whole-pack
    tick reads back as checked rather than as a permanent partial."""
    account = await _account(make_account, "900100001")
    charts = await charts_in_packs(db, {PACK})
    await replace(db, account.id, owned=charts, within=charts)

    counts = {row.pack_id: row for row in await pack_counts(db, account.id)}
    assert counts[PACK].checked
    assert counts[PACK].owned == counts[PACK].total


# --- write scope ------------------------------------------------------------


async def test_replace_leaves_charts_outside_its_scope_alone(
    db: AsyncSession, make_account
):
    account = await _account(make_account, "900100002")
    core = await charts_in_packs(db, {PACK})
    other = await charts_in_packs(db, {"alice"})
    await replace(db, account.id, owned=core | other, within=core | other)

    await replace(db, account.id, owned=set(), within=core)

    left = await declared_chart_ids(db, account.id)
    assert other <= left
    assert left.isdisjoint(core)


async def test_retick_keeps_the_beyond_answer(db: AsyncSession, make_account):
    """A pack menu re-write must not wipe the page it hands off to."""
    account = await _account(make_account, "900100003")
    granted = await charts_in_packs(db, {PACK})
    await replace(db, account.id, owned=granted, within=granted)

    beyond_id = await _a_beyond_of(db, account.id, PACK)
    await replace(db, account.id, owned={beyond_id}, within={beyond_id})

    await replace(db, account.id, owned=granted, within=granted)

    assert beyond_id in await declared_chart_ids(db, account.id)


async def test_untick_takes_the_beyond_with_it(db: AsyncSession, make_account):
    """Otherwise the Beyond row survives as an orphan the picker cannot show and
    the pool filter still counts as playable."""
    account = await _account(make_account, "900100004")
    granted = await charts_in_packs(db, {PACK})
    await replace(db, account.id, owned=granted, within=granted)
    beyond_id = await _a_beyond_of(db, account.id, PACK)
    await replace(db, account.id, owned={beyond_id}, within={beyond_id})

    clearable = await charts_in_packs(db, {PACK}, include_beyond=True)
    await replace(db, account.id, owned=set(), within=clearable)

    # The free base game survives -- unticking one pack is not a full undo.
    left = await declared_chart_ids(db, account.id)
    assert beyond_id not in left
    assert left.isdisjoint(clearable)


# --- what the Beyond page offers --------------------------------------------


async def test_beyond_page_offers_nothing_before_a_declaration(
    db: AsyncSession, make_account
):
    account = await _account(make_account, "900100005")
    assert await beyond_charts(db, account.id) == []


async def test_beyond_page_follows_the_songs_declared(
    db: AsyncSession, make_account
):
    account = await _account(make_account, "900100006")
    granted = await charts_in_packs(db, {PACK})
    await replace(db, account.id, owned=granted, within=granted)

    offered = await beyond_charts(db, account.id)
    assert offered
    for entry in offered:
        # The declared pack, plus the free one that came with it.
        assert entry.song.pack_id in {PACK} | FREE_PACK_IDS
        assert entry.chart.difficulty in (
            DifficultyClass.BYD,
            DifficultyClass.BYD_2,
        )
        assert entry.owned is False


# --- the unconstrained rule -------------------------------------------------


async def test_no_declaration_reads_as_unconstrained(
    db: AsyncSession, make_account
):
    """None, not the empty set: one silent participant must not empty a pool."""
    account = await _account(make_account, "900100007")
    assert await playable_chart_ids(db, account.id) is None


async def test_clearing_returns_to_unconstrained(db: AsyncSession, make_account):
    account = await _account(make_account, "900100008")
    charts = await charts_in_song(db, "lumia")
    await replace(db, account.id, owned=charts, within=charts)
    assert await playable_chart_ids(db, account.id) is not None

    await clear_all(db, account.id)
    assert await playable_chart_ids(db, account.id) is None


# --- the free base game -----------------------------------------------------


async def test_free_pack_is_not_granted_before_any_declaration(
    db: AsyncSession, make_account
):
    """Off the picker must not mean granted on sight -- opening the command and
    closing it would otherwise constrain a player to the base game."""
    account = await _account(make_account, "900100009")
    assert await playable_chart_ids(db, account.id) is None


async def test_first_declaration_brings_the_free_pack(
    db: AsyncSession, make_account
):
    """Nobody is asked about the base game, so a write is the only thing that can
    put it in reach; without this its 64 songs vanish from every pool."""
    account = await _account(make_account, "900100010")
    charts = await charts_in_packs(db, {PACK})
    await replace(db, account.id, owned=charts, within=charts)

    base = await charts_in_packs(db, set(FREE_PACK_IDS))
    assert base
    assert base <= await declared_chart_ids(db, account.id)


async def test_free_pack_beyonds_are_still_asked(db: AsyncSession, make_account):
    """base is in the world-unlock list, so its 20 Beyonds are gated like any
    other and must reach the Beyond page."""
    account = await _account(make_account, "900100011")
    charts = await charts_in_packs(db, {PACK})
    await replace(db, account.id, owned=charts, within=charts)

    packs = {entry.song.pack_id for entry in await beyond_charts(db, account.id)}
    assert packs >= FREE_PACK_IDS


async def test_clearing_removes_the_free_pack_too(db: AsyncSession, make_account):
    account = await _account(make_account, "900100012")
    charts = await charts_in_packs(db, {PACK})
    await replace(db, account.id, owned=charts, within=charts)

    await clear_all(db, account.id)
    assert await declared_chart_ids(db, account.id) == set()


# --- inference from stored plays --------------------------------------------


async def _score_on(db: AsyncSession, account_id: int, song_id: str) -> None:
    """A stored play on a song's Future chart."""
    chart = await db.scalar(
        select(SongDifficulty)
        .where(
            SongDifficulty.song_id == song_id,
            SongDifficulty.difficulty == DifficultyClass.FTR,
        )
    )
    assert chart is not None, song_id
    db.add(
        PlayScore(
            arcaea_account_id=account_id,
            wire_song_id=song_id,
            wire_difficulty=2,
            score=9_800_000,
            time_played=1_700_000_000_000,
            song_difficulty_id=chart.id,
            source="friend",
        )
    )
    await db.flush()


async def test_a_score_proves_its_pack(db: AsyncSession, make_account):
    """`tempestissimo` comes only with Black Fate, so playing it settles the pack."""
    account = await _account(make_account, "900100013")
    await _score_on(db, account.id, "tempestissimo")
    assert await inferred_pack_ids(db, account.id) == {"vs"}


async def test_song_by_song_packs_prove_nothing(db: AsyncSession, make_account):
    """A Memory Archive single, a base-game song and an Extend Archive song are
    each obtainable on their own, so none of them implies the pack."""
    account = await _account(make_account, "900100014")
    await _score_on(db, account.id, "ignotus")  # single
    await _score_on(db, account.id, "vexaria")  # base
    await _score_on(db, account.id, "auxesia")  # extend
    assert await inferred_pack_ids(db, account.id) == set()


async def test_world_unlock_in_a_paid_pack_still_proves_it(
    db: AsyncSession, make_account
):
    """The map ships inside the pack, so reaching the song meant owning it
    (owner, 2026-09-06). Reading `world_unlock` here would drop the inference."""
    account = await _account(make_account, "900100015")
    song = await db.get(Song, "solitarydream")
    assert song.world_unlock and song.pack_id == "core"

    await _score_on(db, account.id, "solitarydream")
    assert "core" in await inferred_pack_ids(db, account.id)


async def test_inference_never_declares_an_account(db: AsyncSession, make_account):
    """Scores in three packs are not a statement that only three are owned."""
    account = await _account(make_account, "900100016")
    await _score_on(db, account.id, "tempestissimo")
    assert await inferred_pack_ids(db, account.id)
    assert await playable_chart_ids(db, account.id) is None


async def test_inferred_packs_reach_the_playable_set(db: AsyncSession, make_account):
    account = await _account(make_account, "900100017")
    charts = await charts_in_packs(db, {PACK})
    await replace(db, account.id, owned=charts, within=charts)
    await _score_on(db, account.id, "tempestissimo")

    playable = await playable_chart_ids(db, account.id)
    assert await charts_in_packs(db, {"vs"}) <= playable


async def test_inferred_packs_are_locked_out_of_the_menus(
    db: AsyncSession, make_account
):
    account = await _account(make_account, "900100018")
    await _score_on(db, account.id, "tempestissimo")
    options = pack_options(
        await pack_counts(db, account.id), await inferred_pack_ids(db, account.id)
    )

    black_fate = next(option for option in options if option.value == "vs")
    assert black_fate.locked
    assert black_fate not in pickable(options)
    assert "Black Fate" in (locked_note(options) or "")
    # Locked still counts as held, or the summary would under-report.
    assert held_count(options) >= 1


async def test_inferred_pack_beyonds_are_still_asked(db: AsyncSession, make_account):
    """Without this, a player whose packs are all inferred opens an empty page."""
    account = await _account(make_account, "900100019")
    await _score_on(db, account.id, "tempestissimo")
    packs = {entry.song.pack_id for entry in await beyond_charts(db, account.id)}
    assert "vs" in packs


async def test_a_played_beyond_is_ticked_and_locked(db: AsyncSession, make_account):
    """Having played it settles the question no declaration could -- so it must
    not be offered as a checkbox. Unticking it would delete a row that changes
    nothing, and the next render would put the tick straight back."""
    account = await _account(make_account, "900100020")
    charts = await charts_in_packs(db, {PACK})
    await replace(db, account.id, owned=charts, within=charts)

    beyond_id = await _a_beyond_of(db, account.id, PACK)
    chart = await db.get(SongDifficulty, beyond_id)
    db.add(
        PlayScore(
            arcaea_account_id=account.id,
            wire_song_id=chart.song_id,
            wire_difficulty=3,
            score=9_500_000,
            time_played=1_700_000_000_000,
            song_difficulty_id=beyond_id,
            source="friend",
        )
    )
    await db.flush()

    entries = await beyond_charts(db, account.id)
    assert beyond_id in {entry.chart.id for entry in entries if entry.owned}
    assert beyond_id in {entry.chart.id for entry in entries if entry.proven}

    options = beyond_options(entries, None)
    played = next(option for option in options if option.value == str(beyond_id))
    assert played.checked and played.locked
    assert played not in pickable(options)


# --- picker labelling -------------------------------------------------------


async def test_singles_and_free_packs_are_not_pickable(db: AsyncSession):
    options = pack_options(await pack_counts(db, -1))
    assert EXCLUDED_PACK_IDS == {"single", "base"}
    assert not any(option.value in EXCLUDED_PACK_IDS for option in options)


async def test_shared_pack_names_are_disambiguated(db: AsyncSession):
    """14 names are shared by 33 packs; an undisambiguated menu shows four rows
    reading 'CHUNITHM Collaboration' and no way to tell them apart."""
    options = pack_options(await pack_counts(db, -1))
    labels = [option.label for option in options]
    assert len(labels) == len(set(labels))


async def test_pack_label_prefers_the_per_song_name(db: AsyncSession):
    """``songs.pack_name`` wins over ``packs.name`` -- extend_3 is stale in the
    pack table and correct on its songs."""
    options = {option.value: option.label for option in pack_options(
        await pack_counts(db, -1)
    )}
    assert options["extend_3"] == "Extend Archive 3"


def test_chunks_fit_one_menu():
    options = [
        Option(value=str(index), label=f"Pack {index:02d}", checked=index % 2 == 0)
        for index in range(62)
    ]
    chunks = chunked(options)
    assert [len(chunk) for chunk in chunks] == [25, 25, 12]
    assert range_label(chunks[0]).startswith("Pack 00 – Pack 24")
    assert "(13 / 25)" in range_label(chunks[0])
