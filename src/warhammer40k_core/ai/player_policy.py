"""Detached player inputs and exact policy routing; no engine authority is exposed."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Protocol, cast

from warhammer40k_core.adapters.projection import (
    PROJECTION_SCHEMA_VERSION,
    DecisionRequestViewPayload,
    GameViewPayload,
)
from warhammer40k_core.engine.event_log import JsonValue, canonical_json, validate_json_value


class PolicyError(ValueError):
    """A policy contract, binding or route failed; execution must stop."""


class CandidateExhaustedError(PolicyError):
    """A policy's declared candidate search exhausted its candidates."""


def payload_digest(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class PolicyRoute:
    actor_id: str
    decision_type: str
    stage: str
    setup_step: str | None
    battle_phase: str | None
    proposal_kind: str | None

    def __post_init__(self) -> None:
        for token in (self.actor_id, self.decision_type):
            if type(token) is not str or not token.strip():
                raise PolicyError("Policy route requires actor and decision identifiers.")
        if self.stage == "setup":
            context, excluded = self.setup_step, self.battle_phase
        elif self.stage == "battle":
            context, excluded = self.battle_phase, self.setup_step
        else:
            raise PolicyError("Policy route requires setup or battle stage.")
        if type(context) is not str or not context.strip() or excluded is not None:
            raise PolicyError("Policy route requires exactly its stage's context.")
        if self.proposal_kind is not None and (
            type(self.proposal_kind) is not str or not self.proposal_kind.strip()
        ):
            raise PolicyError("Policy route proposal kind must be a nonempty identifier.")

    @classmethod
    def from_view(cls, view: GameViewPayload) -> PolicyRoute:
        request = view["pending_decision"]
        if request is None or request["actor_id"] != view["viewer_player_id"]:
            raise PolicyError("Policy observation requires its own pending actor request.")
        if view["viewer_role"] != "player" or request["actor_id"] not in view["player_ids"]:
            raise PolicyError("Policy observation requires a player-scoped projection.")
        interaction = request["interaction"]
        if interaction is None:
            raise PolicyError("Policy request lacks an explicit interaction contract.")
        kind = interaction["proposal_kind"]
        if request["is_parameterized"] != (kind is not None):
            raise PolicyError("Policy request proposal kind and submission kind disagree.")
        return cls(
            request["actor_id"],
            request["decision_type"],
            view["stage"],
            view["current_setup_step"],
            view["current_battle_phase"],
            kind,
        )


@dataclass(frozen=True, slots=True)
class PlayerDecisionContext:
    """Canonical JSON is immutable; each property returns a fresh detached value.

    This is an API boundary for cooperative policies, not a Python security sandbox.
    The choice seed is policy-only and must never be the engine RNG seed.
    """

    route: PolicyRoute
    observation_json: str
    choice_seed: int

    def __post_init__(self) -> None:
        view = self.observation
        if (
            set(view) - set(GameViewPayload.__annotations__)
            or view["projection_schema"] != PROJECTION_SCHEMA_VERSION
        ):
            raise PolicyError("Policy context contains an unknown projection shape or field.")
        pending = view["pending_decision"]
        if pending is not None and set(pending) - set(DecisionRequestViewPayload.__annotations__):
            raise PolicyError("Policy context contains an unknown request view field.")
        if PolicyRoute.from_view(view) != self.route:
            raise PolicyError("Policy context route does not match its observation.")
        if type(self.choice_seed) is not int or self.choice_seed < 0:
            raise PolicyError("Policy choice seed must be a nonnegative integer.")
        # Normalize direct construction too. Hashing this immutable, validated
        # representation needs neither another parse nor another validation walk.
        object.__setattr__(self, "observation_json", canonical_json(view))

    @classmethod
    def from_view(cls, view: GameViewPayload, *, choice_seed: int) -> PlayerDecisionContext:
        return cls(PolicyRoute.from_view(view), canonical_json(view), choice_seed)

    @property
    def observation(self) -> GameViewPayload:
        return cast(GameViewPayload, json.loads(self.observation_json))

    @property
    def request(self) -> DecisionRequestViewPayload:
        request = self.observation["pending_decision"]
        if request is None:
            raise PolicyError("Policy observation lacks its pending request.")
        return request

    @property
    def observation_hash(self) -> str:
        return hashlib.sha256(self.observation_json.encode()).hexdigest()

    def select_option(self, option_id: str) -> PolicyAction:
        return PolicyAction(
            self.route.actor_id, self.request["request_id"], self.observation_hash, option_id, None
        )

    def propose(self, payload: JsonValue) -> PolicyAction:
        return PolicyAction(
            self.route.actor_id,
            self.request["request_id"],
            self.observation_hash,
            None,
            canonical_json(payload),
        )


@dataclass(frozen=True, slots=True)
class PolicyAction:
    actor_id: str
    request_id: str
    observation_hash: str
    option_id: str | None
    proposal_json: str | None

    def __post_init__(self) -> None:
        if (self.option_id is None) == (self.proposal_json is None):
            raise PolicyError("Policy action requires exactly one option or proposal.")
        if self.option_id is not None and (
            type(self.option_id) is not str or not self.option_id.strip()
        ):
            raise PolicyError("Policy action option must be a nonempty identifier.")
        if self.proposal_json is not None:
            try:
                value: object = json.loads(self.proposal_json)
            except (TypeError, json.JSONDecodeError) as exc:
                raise PolicyError("Policy proposal must be JSON.") from exc
            if not isinstance(value, dict):
                raise PolicyError("Policy proposal must be an object.")
            validate_json_value(cast(dict[str, object], value))


class PlayerPolicy(Protocol):
    def choose(self, context: PlayerDecisionContext) -> PolicyAction:
        """Return one bound committed choice, or raise; never request a fallback."""
        ...


@dataclass(frozen=True, slots=True)
class PolicyRegistration:
    route: PolicyRoute
    policy_id: str
    configuration_json: str
    policy: PlayerPolicy

    def __post_init__(self) -> None:
        if type(self.policy_id) is not str or not self.policy_id.strip():
            raise PolicyError("Policy registration requires a versioned policy identifier.")
        try:
            value: object = json.loads(self.configuration_json)
        except (TypeError, json.JSONDecodeError) as exc:
            raise PolicyError("Policy configuration must be JSON.") from exc
        if not isinstance(value, dict):
            raise PolicyError("Policy configuration must be an object.")
        validate_json_value(cast(dict[str, object], value))


class PolicyRouter:
    def __init__(self, registrations: tuple[PolicyRegistration, ...]) -> None:
        self._registrations = {entry.route: entry for entry in registrations}
        if len(self._registrations) != len(registrations):
            raise PolicyError("Duplicate exact policy route.")
        self.identity = payload_digest(
            [
                {
                    "route": [
                        r.actor_id,
                        r.decision_type,
                        r.stage,
                        r.setup_step,
                        r.battle_phase,
                        r.proposal_kind,
                    ],
                    "policy_id": entry.policy_id,
                    "configuration": json.loads(entry.configuration_json),
                }
                for r, entry in sorted(self._registrations.items(), key=lambda item: repr(item[0]))
            ]
        )

    def resolve(self, route: PolicyRoute) -> PolicyRegistration:
        if route not in self._registrations:
            raise PolicyError(f"Unsupported exact policy route: {route}.")
        return self._registrations[route]
