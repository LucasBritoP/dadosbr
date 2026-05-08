from __future__ import annotations

import os

import pytest

from dadosbr.connectors.bcb import fetch_sgs_series


pytestmark = pytest.mark.live


@pytest.mark.skipif(os.getenv("DADOSBR_RUN_LIVE_TESTS") != "1", reason="live tests are opt-in")
def test_live_bcb_sgs_selic_returns_records() -> None:
    response = fetch_sgs_series("11", last=1)

    assert response["ok"] is True
    assert response["records"]
    assert response["records"][0]["series_id"] == "11"
