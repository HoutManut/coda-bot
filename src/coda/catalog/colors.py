"""App-wide Arcaea colors, keyed by domain enum. Reused across extensions;
never redefined per command. Stored as Discord-embed ints.

Shared values are deliberate.
"""

from __future__ import annotations

from coda.db.enums import DifficultyClass, Side

CLASS_COLORS: dict[DifficultyClass, int] = {
    DifficultyClass.PST: 0x2EA2C0,
    DifficultyClass.PRS: 0x94B05C,
    DifficultyClass.FTR: 0x812C64,
    DifficultyClass.BYD: 0xB60F2B,
    DifficultyClass.BYD_2: 0xB60F2B,
    DifficultyClass.ETR: 0x846FA1,
    DifficultyClass.ERR: 0x812C64,
}

SIDE_COLORS: dict[Side, int] = {
    Side.LIGHT: 0x2EA2C0,
    Side.CONFLICT: 0x391749,
    Side.COLORLESS: 0xEAE9E0,
    Side.LEPHON: 0xEAE9E0,
}
