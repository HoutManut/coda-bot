"""``python -m coda.admin`` — launch the admin server (localhost dev tool).

Host/port come from ``ADMIN_HOST`` / ``ADMIN_PORT`` (defaults 127.0.0.1:8727).
Binds loopback by default: this app has no auth and is not for remote exposure.
"""

from __future__ import annotations

import os

import uvicorn


def main() -> None:
    host = os.environ.get("ADMIN_HOST", "127.0.0.1")
    port = int(os.environ.get("ADMIN_PORT", "8727"))
    uvicorn.run("coda.admin.app:app", host=host, port=port, reload=True)


if __name__ == "__main__":
    main()
