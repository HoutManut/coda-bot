"""Tokenizing and verb resolution for ``/run``.

Free text is always submittable, so everything here is what the handler sees
when autocomplete was ignored entirely.
"""

from __future__ import annotations

import pytest

from coda.ops import registry
from coda.settings import REGISTRY, user_keys


def test_tokenize_rejects_unbalanced_quote() -> None:
    with pytest.raises(ValueError):
        registry.tokenize('config set x "half')


def test_suggestions_swallow_unbalanced_quote() -> None:
    assert registry.suggestions('config set x "half') == []


def test_suggestions_offer_verbs_when_empty() -> None:
    assert registry.suggestions("") == list(registry.OPS)


def test_suggestions_rebuild_the_whole_line() -> None:
    assert registry.suggestions("config set polling ") == [
        "config set polling on",
        "config set polling off",
    ]


def test_suggestions_stay_within_discord_caps() -> None:
    rows = registry.suggestions("config get ")
    assert len(rows) <= registry.MAX_SUGGESTIONS
    assert all(len(row) <= registry.MAX_SUGGESTION_LENGTH for row in rows)


def test_owner_keys_are_suggested_only_here() -> None:
    """The terminal reads the registry unfiltered -- that is its purpose."""
    owner_only = set(REGISTRY) - set(user_keys())
    suggested = {row.removeprefix("config get ") for row in registry.suggestions("config get ")}
    assert owner_only and owner_only <= suggested


@pytest.mark.asyncio
async def test_unknown_verb_answers_with_help() -> None:
    result = await registry.dispatch("nope", invoker_id=1)
    assert "Unknown verb" in result.text and "config" in result.text


@pytest.mark.asyncio
async def test_bare_line_is_help() -> None:
    assert (await registry.dispatch("", invoker_id=1)).text == registry.help_text()


@pytest.mark.asyncio
async def test_verb_help_is_that_verbs_grammar() -> None:
    result = await registry.dispatch("config help", invoker_id=1)
    assert result.text == registry.help_text(registry.OPS["config"])


@pytest.mark.asyncio
async def test_unknown_key_never_reaches_the_database() -> None:
    result = await registry.dispatch("config get not_a_key", invoker_id=1)
    assert result.text == "Unknown setting `not_a_key`."
