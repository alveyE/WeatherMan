"""Polymarket CLOB client setup for live trading."""

import os
from typing import Optional

# Lazy import - py-clob-client may not be installed in paper mode
_clob_client = None


def get_client():
    """Create or return cached ClobClient. Requires PRIVATE_KEY and FUNDER_ADDRESS."""
    global _clob_client
    if _clob_client is not None:
        return _clob_client

    try:
        from py_clob_client.client import ClobClient
    except ImportError:
        raise ImportError("py-clob-client required for live trading. pip install py-clob-client")

    key = os.environ.get("PRIVATE_KEY")
    funder = os.environ.get("FUNDER_ADDRESS")
    if not key or not funder:
        raise ValueError("PRIVATE_KEY and FUNDER_ADDRESS must be set for live trading")

    # signature_type: 0=EOA, 1=Magic/email, 2=Gnosis Safe/browser proxy
    sig_type = int(os.environ.get("SIGNATURE_TYPE", "1"))

    _clob_client = ClobClient(
        "https://clob.polymarket.com",
        key=key,
        chain_id=137,
        signature_type=sig_type,
        funder=funder,
    )
    _clob_client.set_api_creds(_clob_client.create_or_derive_api_creds())
    return _clob_client
