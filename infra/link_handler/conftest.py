import sys

import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "asyncio: mark test as async")
    config.addinivalue_line("markers", "network: mark test as requiring live internet and a running Oxigraph instance")
    config.addinivalue_line("markers", "host_check: keep the public-host check (tests serve from 127.0.0.1, so it is off otherwise)")


@pytest.fixture(autouse=True)
def _local_test_servers(request, monkeypatch):
    """The test servers listen on 127.0.0.1, which the map refuses to fetch (source.non_public_host)."""
    main = sys.modules.get("main")
    if main is not None and "host_check" not in request.keywords:
        async def allow(url):
            return None
        monkeypatch.setattr(main, "_host_error", allow)
