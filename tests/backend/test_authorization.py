import pytest

from app.security.sessions import role_is_enabled

from app.security.authorization import (
    AuthorizationError,
    has_any_role,
    require_any_role,
)


def test_has_any_role_returns_true_for_matching_role() -> None:
    assert has_any_role(
        user_roles=["executor", "engineer"],
        allowed_roles=["admin", "engineer"],
    )


def test_has_any_role_returns_false_without_matching_role() -> None:
    assert not has_any_role(
        user_roles=["executor"],
        allowed_roles=["admin", "dispatcher"],
    )


def test_has_any_role_returns_false_for_empty_user_roles() -> None:
    assert not has_any_role(
        user_roles=[],
        allowed_roles=["admin"],
    )


def test_has_any_role_rejects_empty_allowed_roles() -> None:
    with pytest.raises(ValueError, match="allowed_roles must not be empty"):
        has_any_role(
            user_roles=["admin"],
            allowed_roles=[],
        )


def test_require_any_role_allows_matching_role() -> None:
    require_any_role(
        user_roles=["dispatcher"],
        allowed_roles=["admin", "dispatcher"],
    )


def test_require_any_role_rejects_non_matching_role() -> None:
    with pytest.raises(
        AuthorizationError,
        match="User does not have the required role",
    ):
        require_any_role(
            user_roles=["executor"],
            allowed_roles=["admin", "dispatcher"],
        )


def test_require_any_role_rejects_empty_user_roles() -> None:
    with pytest.raises(AuthorizationError):
        require_any_role(
            user_roles=[],
            allowed_roles=["admin"],
        )


def test_role_gate_accepts_target_profile(monkeypatch) -> None:
    monkeypatch.setenv("FIXRATE_ACTIVE_ROLES", "chief_engineer,executor,admin")
    assert role_is_enabled("chief_engineer")
    assert role_is_enabled("executor")
    assert role_is_enabled("admin")
    assert not role_is_enabled("director")
    assert not role_is_enabled("dispatcher")
    assert not role_is_enabled("engineer")


def test_role_gate_preserves_empty_compatibility_profile(monkeypatch) -> None:
    monkeypatch.setenv("FIXRATE_ACTIVE_ROLES", "")
    assert role_is_enabled("director")
    assert role_is_enabled("engineer")
