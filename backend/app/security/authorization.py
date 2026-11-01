from collections.abc import Iterable
from typing import TypeVar


UserT = TypeVar("UserT")


class AuthorizationError(PermissionError):
    """Raised when a user does not have the required role."""


def has_any_role(
    user_roles: Iterable[str],
    allowed_roles: Iterable[str],
) -> bool:
    """Return True if the user has at least one allowed role.

    An empty set of user roles never grants access.
    An empty set of allowed roles is considered a configuration error.
    """
    allowed = frozenset(allowed_roles)
    if not allowed:
        raise ValueError("allowed_roles must not be empty")

    assigned = frozenset(user_roles)
    return bool(assigned & allowed)


def require_any_role(
    user_roles: Iterable[str],
    allowed_roles: Iterable[str],
) -> None:
    """Raise AuthorizationError unless the user has an allowed role."""
    if not has_any_role(user_roles, allowed_roles):
        raise AuthorizationError("User does not have the required role")
