"""Immutable engine-enumerated candidates over one detached player observation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TypedDict, cast

from warhammer40k_core.ai.player_policy import (
    CandidateExhaustedError,
    PlayerDecisionContext,
    PolicyAction,
    PolicyError,
    payload_digest,
)
from warhammer40k_core.engine.decision_request import (
    DecisionError,
    DecisionOption,
    DecisionOptionPayload,
)
from warhammer40k_core.engine.event_log import EventLogError, canonical_json, validate_json_value

FINITE_CANDIDATE_SCHEMA_VERSION = "finite-candidate-set-v1"
FINITE_CANDIDATE_GENERATOR_ID = "player-view-finite-options-v1"
FINITE_CANDIDATE_VALIDATION_ID = "engine-enumerated-options-v1"


class FiniteCandidateSetPayload(TypedDict):
    schema_version: str
    generator_id: str
    validation_id: str
    actor_id: str
    request_id: str
    observation_hash: str
    options: list[DecisionOptionPayload]


def _identifier(value: object) -> str:
    if type(value) is not str or not value.strip():
        raise PolicyError("Finite candidate binding requires nonempty identifiers.")
    return value


@dataclass(frozen=True, slots=True)
class FiniteCandidate:
    """Canonical bytes own the complete option; access returns a detached copy."""

    option_json: str

    def __post_init__(self) -> None:
        try:
            option: object = json.loads(self.option_json)
        except (TypeError, json.JSONDecodeError) as exc:
            raise PolicyError("Finite candidate option must be JSON.") from exc
        if (
            not isinstance(option, dict)
            or option.keys() != DecisionOptionPayload.__annotations__.keys()
        ):
            raise PolicyError("Finite candidate requires exactly the option payload fields.")
        try:
            validated = DecisionOption.from_payload(cast(DecisionOptionPayload, option))
        except (DecisionError, EventLogError) as exc:
            raise PolicyError("Finite candidate option is malformed.") from exc
        object.__setattr__(self, "option_json", canonical_json(validated.to_payload()))

    @classmethod
    def from_payload(cls, payload: object) -> FiniteCandidate:
        try:
            validate_json_value(payload)
        except EventLogError as exc:
            raise PolicyError("Finite candidate option must be JSON-safe.") from exc
        return cls(canonical_json(payload))

    @property
    def option(self) -> DecisionOptionPayload:
        return cast(DecisionOptionPayload, json.loads(self.option_json))

    @property
    def candidate_id(self) -> str:
        return self.option["option_id"]

    @property
    def content_hash(self) -> str:
        return payload_digest(self.option)


@dataclass(frozen=True, slots=True)
class FiniteCandidateSet:
    """An ordered complete option mapping, bound to one player request snapshot.

    Loading verifies structure; select additionally verifies the exact current
    context. Engine validation and mutation remain with the ordinary runner.
    """

    actor_id: str
    request_id: str
    observation_hash: str
    candidates: tuple[FiniteCandidate, ...]

    def __post_init__(self) -> None:
        _identifier(self.actor_id)
        _identifier(self.request_id)
        digest = _identifier(self.observation_hash)
        if len(digest) != 64 or set(digest) - set("0123456789abcdef"):
            raise PolicyError("Finite candidate observation hash must be lowercase SHA-256.")
        if type(self.candidates) is not tuple or any(
            type(candidate) is not FiniteCandidate for candidate in self.candidates
        ):
            raise PolicyError("Finite candidates must be an immutable typed tuple.")
        if not self.candidates:
            raise CandidateExhaustedError("Finite request has no engine-enumerated candidates.")
        if len(set(self.candidate_ids)) != len(self.candidates):
            raise PolicyError("Finite candidate IDs must be unique.")

    @classmethod
    def from_context(cls, context: PlayerDecisionContext) -> FiniteCandidateSet:
        request = context.request
        if request["is_parameterized"] or context.route.proposal_kind is not None:
            raise PolicyError("Parameterized requests require a proposal candidate contract.")
        return cls(
            actor_id=context.route.actor_id,
            request_id=request["request_id"],
            observation_hash=context.observation_hash,
            candidates=tuple(FiniteCandidate.from_payload(option) for option in request["options"]),
        )

    @property
    def candidate_ids(self) -> tuple[str, ...]:
        return tuple(candidate.candidate_id for candidate in self.candidates)

    @property
    def content_hash(self) -> str:
        return payload_digest(self.to_payload())

    def select(self, context: PlayerDecisionContext, candidate_id: str) -> PolicyAction:
        if self != type(self).from_context(context):
            raise PolicyError("Finite candidate binding or ordered option payloads drifted.")
        if candidate_id not in self.candidate_ids:
            raise PolicyError("Selected candidate is not in the finite set.")
        return context.select_option(candidate_id)

    def to_payload(self) -> FiniteCandidateSetPayload:
        return {
            "schema_version": FINITE_CANDIDATE_SCHEMA_VERSION,
            "generator_id": FINITE_CANDIDATE_GENERATOR_ID,
            "validation_id": FINITE_CANDIDATE_VALIDATION_ID,
            "actor_id": self.actor_id,
            "request_id": self.request_id,
            "observation_hash": self.observation_hash,
            "options": [candidate.option for candidate in self.candidates],
        }

    @classmethod
    def from_payload(cls, payload: object) -> FiniteCandidateSet:
        if (
            not isinstance(payload, dict)
            or payload.keys() != FiniteCandidateSetPayload.__annotations__.keys()
        ):
            raise PolicyError("Finite candidate set has missing or unknown fields.")
        value = cast(dict[str, object], payload)
        if (
            value["schema_version"] != FINITE_CANDIDATE_SCHEMA_VERSION
            or value["generator_id"] != FINITE_CANDIDATE_GENERATOR_ID
            or value["validation_id"] != FINITE_CANDIDATE_VALIDATION_ID
        ):
            raise PolicyError("Unknown finite candidate schema, generator or validation identity.")
        options = value["options"]
        if type(options) is not list:
            raise PolicyError("Finite candidate options must be a list.")
        return cls(
            actor_id=_identifier(value["actor_id"]),
            request_id=_identifier(value["request_id"]),
            observation_hash=_identifier(value["observation_hash"]),
            candidates=tuple(
                FiniteCandidate.from_payload(option) for option in cast(list[object], options)
            ),
        )
