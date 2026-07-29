"""``parse_value`` is what stops an int key being stored as a string."""

from __future__ import annotations

import pytest

from coda.settings.parse import parse_value
from coda.settings.types import ConfigKey, Scope

CHAINS = {"guild_chain": (Scope.GLOBAL,), "dm_chain": (Scope.GLOBAL,)}


def key(name: str, default: object, type_: object) -> ConfigKey:
    return ConfigKey(name=name, default=default, type=type_, **CHAINS)  # type: ignore[arg-type]


def test_int_key_coerces() -> None:
    assert parse_value(key("window", 20, "int"), "25") == 25


def test_int_key_rejects_non_number() -> None:
    with pytest.raises(ValueError):
        parse_value(key("window", 20, "int"), "twenty")


@pytest.mark.parametrize(("raw", "expected"), [("on", True), ("off", False), ("TRUE", True)])
def test_bool_key(raw: str, expected: bool) -> None:
    assert parse_value(key("flag", True, "bool"), raw) is expected


def test_enum_key_rejects_outsider() -> None:
    with pytest.raises(ValueError):
        parse_value(key("locale", "en", ("en", "ja")), "de")


def test_enum_key_accepts_member() -> None:
    assert parse_value(key("locale", "en", ("en", "ja")), "ja") == "ja"


def test_timezone_key_rejects_unknown_zone() -> None:
    # parse_zone falls back silently at read time, so the set path is the only
    # place a typo can still be reported.
    with pytest.raises(ValueError):
        parse_value(key("timezone", "Asia/Bangkok", "timezone"), "Nonsense/Zone")


def test_timezone_key_accepts_iana_name() -> None:
    assert parse_value(key("timezone", "Asia/Bangkok", "timezone"), "Asia/Tokyo") == "Asia/Tokyo"


def test_str_key_passes_through() -> None:
    assert parse_value(key("epoch", "2026-07-27", "str"), "2026-01-01") == "2026-01-01"
