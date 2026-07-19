from __future__ import annotations

import hmac
from dataclasses import dataclass
from enum import StrEnum
from typing import Self

from warhammer40k_core.core.validation import IdentifierValidator


class AccessControlError(ValueError):
    """Raised when authenticated adapter identity or role policy is invalid."""


class AuthenticationError(AccessControlError):
    """Raised when an opaque bearer credential cannot be authenticated."""


class AuthorizationError(AccessControlError):
    """Raised when an authenticated principal is not bound to the requested session."""


class PrincipalRole(StrEnum):
    PLAYER = "player"
    COACH = "coach"
    DELAYED_SPECTATOR = "delayed_spectator"
    ADMINISTRATOR = "administrator"
    REPLAY_VIEWER = "replay_viewer"


@dataclass(frozen=True, slots=True)
class RolePolicy:
    role: PrincipalRole
    may_create_session: bool
    may_mutate_lifecycle: bool
    may_submit_decision: bool
    may_view_live: bool
    may_view_catalog: bool
    may_view_support: bool
    may_export_replay: bool
    omniscient: bool
    delay_revisions: int

    def __post_init__(self) -> None:
        if type(self.role) is not PrincipalRole:
            raise AccessControlError("Role policy requires a PrincipalRole.")
        flags = (
            self.may_create_session,
            self.may_mutate_lifecycle,
            self.may_submit_decision,
            self.may_view_live,
            self.may_view_catalog,
            self.may_view_support,
            self.may_export_replay,
            self.omniscient,
        )
        if any(type(value) is not bool for value in flags):
            raise AccessControlError("Role policy flags must be bool values.")
        if type(self.delay_revisions) is not int or self.delay_revisions < 0:
            raise AccessControlError("Role policy delay must be a non-negative integer.")
        if self.delay_revisions and self.role is not PrincipalRole.DELAYED_SPECTATOR:
            raise AccessControlError("Only delayed spectators may have a revision delay.")


ROLE_POLICY_BY_ROLE: dict[PrincipalRole, RolePolicy] = {
    PrincipalRole.PLAYER: RolePolicy(
        role=PrincipalRole.PLAYER,
        may_create_session=False,
        may_mutate_lifecycle=False,
        may_submit_decision=True,
        may_view_live=True,
        may_view_catalog=True,
        may_view_support=True,
        may_export_replay=False,
        omniscient=False,
        delay_revisions=0,
    ),
    PrincipalRole.COACH: RolePolicy(
        role=PrincipalRole.COACH,
        may_create_session=False,
        may_mutate_lifecycle=False,
        may_submit_decision=False,
        may_view_live=True,
        may_view_catalog=True,
        may_view_support=True,
        may_export_replay=False,
        omniscient=False,
        delay_revisions=0,
    ),
    PrincipalRole.DELAYED_SPECTATOR: RolePolicy(
        role=PrincipalRole.DELAYED_SPECTATOR,
        may_create_session=False,
        may_mutate_lifecycle=False,
        may_submit_decision=False,
        may_view_live=True,
        may_view_catalog=True,
        may_view_support=False,
        may_export_replay=False,
        omniscient=False,
        delay_revisions=1,
    ),
    PrincipalRole.ADMINISTRATOR: RolePolicy(
        role=PrincipalRole.ADMINISTRATOR,
        may_create_session=True,
        may_mutate_lifecycle=True,
        may_submit_decision=False,
        may_view_live=True,
        may_view_catalog=True,
        may_view_support=True,
        may_export_replay=True,
        omniscient=True,
        delay_revisions=0,
    ),
    PrincipalRole.REPLAY_VIEWER: RolePolicy(
        role=PrincipalRole.REPLAY_VIEWER,
        may_create_session=False,
        may_mutate_lifecycle=False,
        may_submit_decision=False,
        may_view_live=False,
        may_view_catalog=True,
        may_view_support=False,
        may_export_replay=True,
        omniscient=False,
        delay_revisions=0,
    ),
}


@dataclass(frozen=True, slots=True)
class AuthenticatedPrincipal:
    principal_id: str
    role: PrincipalRole
    player_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "principal_id",
            _validate_identifier("principal_id", self.principal_id),
        )
        if type(self.role) is not PrincipalRole:
            raise AccessControlError("Authenticated principal role is invalid.")
        if self.role in {PrincipalRole.PLAYER, PrincipalRole.COACH}:
            object.__setattr__(
                self,
                "player_id",
                _validate_identifier("principal player_id", self.player_id),
            )
        elif self.player_id is not None:
            raise AccessControlError("This principal role cannot bind to a player.")

    @property
    def policy(self) -> RolePolicy:
        return ROLE_POLICY_BY_ROLE[self.role]

    def bind_to_session(self, *, player_ids: tuple[str, ...]) -> ViewerContext:
        players = _validated_player_ids(player_ids)
        if self.player_id is not None and self.player_id not in players:
            raise AuthorizationError("Authenticated principal is not bound to this session.")
        return ViewerContext(
            principal_id=self.principal_id,
            role=self.role,
            viewer_player_id=self.player_id,
            policy=self.policy,
        )


@dataclass(frozen=True, slots=True)
class ViewerContext:
    principal_id: str
    role: PrincipalRole
    viewer_player_id: str | None
    policy: RolePolicy

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "principal_id",
            _validate_identifier("viewer principal_id", self.principal_id),
        )
        if type(self.role) is not PrincipalRole or self.policy.role is not self.role:
            raise AccessControlError("Viewer context role policy is inconsistent.")
        if self.role in {PrincipalRole.PLAYER, PrincipalRole.COACH}:
            object.__setattr__(
                self,
                "viewer_player_id",
                _validate_identifier("viewer_player_id", self.viewer_player_id),
            )
        elif self.viewer_player_id is not None:
            raise AccessControlError("This viewer role cannot bind to a player.")

    @classmethod
    def for_player(cls, player_id: str) -> Self:
        player = _validate_identifier("viewer_player_id", player_id)
        return cls(
            principal_id=f"local-player:{player}",
            role=PrincipalRole.PLAYER,
            viewer_player_id=player,
            policy=ROLE_POLICY_BY_ROLE[PrincipalRole.PLAYER],
        )

    @property
    def cursor_scope(self) -> str:
        player_scope = "shared" if self.viewer_player_id is None else self.viewer_player_id
        return f"{self.role.value}:{player_scope}:{self.policy.delay_revisions}"

    def owns_player(self, player_id: str | None) -> bool:
        return player_id is not None and self.viewer_player_id == player_id


@dataclass(frozen=True, slots=True)
class PrincipalCredential:
    token: str
    principal: AuthenticatedPrincipal

    def __post_init__(self) -> None:
        object.__setattr__(self, "token", _validate_secret(self.token))
        if type(self.principal) is not AuthenticatedPrincipal:
            raise AccessControlError("Principal credential requires a typed principal.")


@dataclass(frozen=True, slots=True)
class PrincipalRegistry:
    credentials: tuple[PrincipalCredential, ...]

    def __post_init__(self) -> None:
        if type(self.credentials) is not tuple or not self.credentials:
            raise AccessControlError("Principal registry requires credentials.")
        seen_tokens: set[str] = set()
        seen_principals: set[str] = set()
        for credential in self.credentials:
            if type(credential) is not PrincipalCredential:
                raise AccessControlError("Principal registry credential is invalid.")
            if credential.token in seen_tokens:
                raise AccessControlError("Principal registry tokens must be unique.")
            if credential.principal.principal_id in seen_principals:
                raise AccessControlError("Principal registry IDs must be unique.")
            seen_tokens.add(credential.token)
            seen_principals.add(credential.principal.principal_id)

    def authenticate(self, authorization: str | None) -> AuthenticatedPrincipal:
        token = _bearer_token(authorization)
        for credential in self.credentials:
            if hmac.compare_digest(credential.token, token):
                return credential.principal
        raise AuthenticationError("Bearer credential was not authenticated.")

    def validate_player_bindings(self, *, player_ids: tuple[str, ...]) -> None:
        players = _validated_player_ids(player_ids)
        bound_players = {
            credential.principal.player_id
            for credential in self.credentials
            if credential.principal.role is PrincipalRole.PLAYER
            and credential.principal.player_id in players
        }
        if bound_players != set(players):
            raise AuthorizationError("Every session player requires a server-owned principal.")


DEV_ADMIN_TOKEN = "core-v2-dev-administrator"
DEV_PLAYER_A_TOKEN = "core-v2-dev-player-a"
DEV_PLAYER_B_TOKEN = "core-v2-dev-player-b"
DEV_COACH_A_TOKEN = "core-v2-dev-coach-a"
DEV_SPECTATOR_TOKEN = "core-v2-dev-delayed-spectator"
DEV_REPLAY_TOKEN = "core-v2-dev-replay-viewer"


def default_principal_registry() -> PrincipalRegistry:
    return PrincipalRegistry(
        credentials=(
            PrincipalCredential(
                token=DEV_PLAYER_A_TOKEN,
                principal=AuthenticatedPrincipal(
                    principal_id="principal-player-a",
                    role=PrincipalRole.PLAYER,
                    player_id="player-a",
                ),
            ),
            PrincipalCredential(
                token=DEV_PLAYER_B_TOKEN,
                principal=AuthenticatedPrincipal(
                    principal_id="principal-player-b",
                    role=PrincipalRole.PLAYER,
                    player_id="player-b",
                ),
            ),
            PrincipalCredential(
                token=DEV_COACH_A_TOKEN,
                principal=AuthenticatedPrincipal(
                    principal_id="principal-coach-a",
                    role=PrincipalRole.COACH,
                    player_id="player-a",
                ),
            ),
            PrincipalCredential(
                token=DEV_SPECTATOR_TOKEN,
                principal=AuthenticatedPrincipal(
                    principal_id="principal-delayed-spectator",
                    role=PrincipalRole.DELAYED_SPECTATOR,
                ),
            ),
            PrincipalCredential(
                token=DEV_ADMIN_TOKEN,
                principal=AuthenticatedPrincipal(
                    principal_id="principal-administrator",
                    role=PrincipalRole.ADMINISTRATOR,
                ),
            ),
            PrincipalCredential(
                token=DEV_REPLAY_TOKEN,
                principal=AuthenticatedPrincipal(
                    principal_id="principal-replay-viewer",
                    role=PrincipalRole.REPLAY_VIEWER,
                ),
            ),
        )
    )


def bearer_authorization(token: str) -> str:
    return f"Bearer {_validate_secret(token)}"


def _bearer_token(value: str | None) -> str:
    if type(value) is not str:
        raise AuthenticationError("Bearer credential is required.")
    prefix = "Bearer "
    if not value.startswith(prefix):
        raise AuthenticationError("Bearer credential is required.")
    token = value[len(prefix) :].strip()
    if not token or len(token) > 256:
        raise AuthenticationError("Bearer credential is required.")
    return token


def _validate_secret(value: object) -> str:
    if type(value) is not str:
        raise AccessControlError("Credential must be a string.")
    stripped = value.strip()
    if not stripped or len(stripped) > 256:
        raise AccessControlError("Credential length is invalid.")
    return stripped


def _validated_player_ids(values: tuple[str, ...]) -> tuple[str, ...]:
    if type(values) is not tuple or not values:
        raise AccessControlError("Session player IDs must be a non-empty tuple.")
    players = tuple(_validate_identifier("player_id", value) for value in values)
    if len(players) != len(set(players)):
        raise AccessControlError("Session player IDs must be unique.")
    return players


_validate_identifier = IdentifierValidator(AccessControlError)
