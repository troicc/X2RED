from __future__ import annotations

import os

import pytest

from app.core.config import Settings, get_settings


_PROXY_ENV_KEYS = (
    "ALL_PROXY",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "NO_PROXY",
    "all_proxy",
    "http_proxy",
    "https_proxy",
    "no_proxy",
)


@pytest.fixture(autouse=True)
def isolate_tests_from_local_runtime_config(
    monkeypatch: pytest.MonkeyPatch,
):
    """Keep repository-local secrets and host proxies out of every test.

    Production still loads ``.env`` through ``Settings.model_config``. Tests must
    opt into every setting explicitly so running them from the repository root is
    equivalent to CI and cannot accidentally call a configured external model.
    """

    monkeypatch.setitem(Settings.model_config, "env_file", None)
    for key in tuple(os.environ):
        if key.startswith("X2RED_") or key in _PROXY_ENV_KEYS:
            monkeypatch.delenv(key, raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
