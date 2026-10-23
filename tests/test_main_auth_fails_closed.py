"""F-240: api.main must not start with a silent no-op in place of its REST authentication middleware."""

import importlib
import sys

import pytest


def _isolate_api_main(monkeypatch: pytest.MonkeyPatch) -> None:
    """Re-importing api.main rebinds the `api.main` attribute of the package: restore it afterwards,
    or later tests that patch `api.main` would patch the throwaway module instead of the served one."""
    import api
    import api.main as served_main

    monkeypatch.setattr(api, "main", served_main)
    monkeypatch.delitem(sys.modules, "api.main", raising=False)


def test_startup_fails_when_auth_middleware_cannot_be_imported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import api.auth_middleware  # noqa: F401  (make sure the real module is loaded before it is hidden)

    # A None entry in sys.modules makes `import` raise ImportError, whatever the module path.
    monkeypatch.setitem(sys.modules, "api.auth_middleware", None)
    monkeypatch.setitem(sys.modules, "auth_middleware", None)
    _isolate_api_main(monkeypatch)

    with pytest.raises(ImportError):
        importlib.import_module("api.main")


def test_main_has_no_auth_fallback_and_uses_the_package_middleware(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Before F-240 a failing top-level ``auth_middleware`` import left `require_auth` as a no-op `dev-client`."""
    import api.auth_middleware

    monkeypatch.setitem(
        sys.modules, "auth_middleware", None
    )  # the old, path-hacked import location
    _isolate_api_main(monkeypatch)

    main = importlib.import_module("api.main")

    assert main.require_auth is api.auth_middleware.require_auth
    assert main.optional_auth is api.auth_middleware.optional_auth
    assert not hasattr(main, "AUTH_AVAILABLE")  # the "development mode" switch is gone
