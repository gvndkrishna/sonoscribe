"""Use the macOS Keychain for TLS in frozen builds (Zscaler and other corp CAs)."""

from __future__ import annotations

import os


def _configure() -> None:
    if os.environ.get("SSL_CERT_FILE") or os.environ.get("REQUESTS_CA_BUNDLE"):
        return
    try:
        import truststore

        truststore.inject_into_ssl()
    except Exception:
        return


_configure()
