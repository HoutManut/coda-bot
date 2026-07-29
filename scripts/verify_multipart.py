#!/usr/bin/env python
"""Check the live API still accepts the multipart body ``endpoints.add_friend`` sends.

**History — do not undo this.** `arcaea-api-layer.md` §10 gated `add_friend` on
verifying `aiohttp.FormData` against the wire. It was verified 2026-07-17 and it
**FAILED**: `FormData` makes `POST /webapi/friend/me/add` hang until Cloudflare
returns a 504, because it streams with `Transfer-Encoding: chunked` and no
`Content-Length`, and lowiro's origin waits forever for a body it never decides
has ended. A hand-built `bytes` body gets a `Content-Length` and answers normally
in the same session, seconds apart. Hence `client.encode_multipart`.

So this script now guards the fix rather than choosing it. Re-run it after any
lowiro change; if it fails, `encode_multipart` is the first suspect.

    ARCAEA_EMAIL=... ARCAEA_PASSWORD=... uv run python scripts/verify_multipart.py

Non-destructive: the default code `000000000` does not exist, so a PASS adds
nobody and burns no friend slot. `error_code: 401` is the pass -- the server can
only answer "user not found" by parsing the body and reading the field.

Credentials are the lowiro email *or username* of a bot account (username works
-- observed 2026-07-17), never your main.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys

from coda.arcaea import auth, endpoints
from coda.arcaea.client import close, encode_multipart
from coda.arcaea.errors import (
    AlreadyFriend,
    ArcaeaError,
    InvalidCredentials,
    PlayerNotFound,
    UnexpectedResponse,
)

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")


def show_body() -> None:
    """Print the exact bytes we send, so a wire diff is possible by eye."""
    body, content_type = encode_multipart({"friend_code": "000000000"})
    print("Content-Type:", content_type)
    print("Content-Length:", len(body), "(set by aiohttp, because this is bytes)")
    print("--- body ---")
    print(body.decode().replace("\r\n", "\\r\\n\n"), end="")
    print("--- end ---\n")


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--code",
        default="000000000",
        help="friend code to submit (default: 000000000, nonexistent, adds nobody)",
    )
    parser.add_argument("--show-body", action="store_true", help="print the body and exit")
    args = parser.parse_args()

    if args.show_body:
        show_body()
        return 0

    email, password = os.environ.get("ARCAEA_EMAIL"), os.environ.get("ARCAEA_PASSWORD")
    if not email or not password:
        print(
            "Set ARCAEA_EMAIL and ARCAEA_PASSWORD (a bot account, not your main).",
            file=sys.stderr,
        )
        return 1

    if args.code != "000000000":
        print(f"Using {args.code} -- this may REALLY add a friend.")

    try:
        print("Logging in...")
        sid, _ = await auth.login(email, password)

        print(f"POST /webapi/friend/me/add (hand-built multipart, code={args.code})...")
        await endpoints.add_friend(sid, args.code)

    except PlayerNotFound:
        print(
            "\nPASS: error_code 401 (user not found).\n"
            "      lowiro could only answer that by parsing our multipart body and\n"
            "      reading friend_code. The encoder is accepted."
        )
        return 0
    except AlreadyFriend:
        print("\nPASS: error_code 602 (already a friend) -- body parsed fine.")
        return 0
    except InvalidCredentials:
        print("\nFAIL: login rejected. Check the credentials.", file=sys.stderr)
        return 1
    except UnexpectedResponse as exc:
        # This is what the FormData regression looked like: a Cloudflare HTML 504
        # instead of JSON, because the origin never saw the body end.
        print(
            f"\nFAIL: {exc}\n"
            "      A non-JSON reply (HTML 504) means the body was never accepted.\n"
            "      Did someone swap encode_multipart back to aiohttp.FormData?",
            file=sys.stderr,
        )
        return 1
    except ArcaeaError as exc:
        print(f"\nFAIL: unexpected {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    else:
        print("\nPASS: success -- a friend was really added. Remove it if unintended.")
        return 0
    finally:
        await close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
