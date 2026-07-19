from __future__ import annotations

from warhammer40k_core.adapters.access_control import (
    AccessControlError,
    AuthorizationError,
    ViewerContext,
)
from warhammer40k_core.adapters.session_protocol import AuthoritativeSession, SessionState


def actor_not_authorized() -> AuthorizationError:
    return AuthorizationError("Authenticated principal is not authorized for this operation.")


def require_permission(allowed: bool) -> None:
    if type(allowed) is not bool:
        raise AccessControlError("Authorization policy value must be bool.")
    if not allowed:
        raise AuthorizationError("Authenticated principal lacks route permission.")


def require_replay_export_allowed(
    *,
    record: AuthoritativeSession,
    viewer: ViewerContext,
) -> None:
    if viewer.policy.omniscient:
        return
    if record.state not in {SessionState.TERMINAL, SessionState.CLOSED}:
        raise AuthorizationError("Non-live replay export is unavailable for an active session.")
