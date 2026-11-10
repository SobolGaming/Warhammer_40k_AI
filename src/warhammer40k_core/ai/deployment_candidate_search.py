"""Bounded actor-view translations of a supplied deployment formation."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from enum import StrEnum
from typing import cast

from warhammer40k_core.ai.deployment_candidates import DeploymentPlacementCandidate
from warhammer40k_core.ai.player_policy import (
    CandidateExhaustedError,
    PlayerDecisionContext,
    PolicyError,
    payload_digest,
)
from warhammer40k_core.engine.event_log import (
    EventLogError,
    JsonValue,
    canonical_json,
    validate_json_value,
)

DEPLOYMENT_SET_SCHEMA = "deployment-translation-set-v1"
DEPLOYMENT_GENERATOR = "actor-formation-xy-translations-v1"
# Preserve the original seed/one-inch prefix for callers with smaller budgets.
# The second cardinal ring adds wider spatial alternatives; legality still belongs
# exclusively to ordinary engine validation, and no tactical quality is implied.
DEFAULT_TRANSLATIONS = (
    (0.0, 0.0),
    (1.0, 0.0),
    (-1.0, 0.0),
    (0.0, 1.0),
    (0.0, -1.0),
    (2.0, 0.0),
    (-2.0, 0.0),
    (0.0, 2.0),
    (0.0, -2.0),
)


class DeploymentSearchStop(StrEnum):
    COMPLETE = "complete"
    RAW_BUDGET = "raw_budget"
    VALIDATION_BUDGET = "validation_budget"
    ACCEPTED_LIMIT = "accepted_limit"


class DeploymentCandidateExhaustedError(CandidateExhaustedError):
    """No candidate survived the declared search; this is not a rules proof."""

    def __init__(
        self,
        *,
        stop_reason: DeploymentSearchStop,
        raw_attempts: int,
        duplicates: int,
        validation_attempts: int = 0,
    ) -> None:
        self.stop_reason = stop_reason
        self.raw_attempts = raw_attempts
        self.duplicates = duplicates
        self.validation_attempts = validation_attempts
        super().__init__(
            f"Deployment candidates exhausted: {stop_reason}; raw={raw_attempts}, "
            f"duplicates={duplicates}, validations={validation_attempts}."
        )


def require_budget(value: object, *, maximum: int) -> int:
    if type(value) is not int or not 0 <= value <= maximum:
        raise PolicyError(f"Deployment budget must be an integer in [0, {maximum}].")
    return value


def _number(value: object) -> float:
    if type(value) not in (float, int):
        raise PolicyError("Deployment translation coordinates must be finite numbers.")
    try:
        number = float(cast(float | int, value))
    except OverflowError as exc:
        raise PolicyError("Deployment translation coordinates must be finite numbers.") from exc
    if not math.isfinite(number):
        raise PolicyError("Deployment translation coordinates must be finite numbers.")
    return 0.0 if number == 0 else number


def _translated(proposal: JsonValue, dx: float, dy: float) -> JsonValue:
    if not isinstance(proposal, dict):
        raise PolicyError("Deployment seed must be a proposal object.")
    placements = proposal.get("model_placements")
    if not isinstance(placements, list) or not placements:
        raise PolicyError("Deployment seed requires model placements.")
    for placement in placements:
        if not isinstance(placement, dict) or not isinstance(placement.get("pose"), dict):
            raise PolicyError("Deployment seed requires model poses.")
        pose = cast(dict[str, JsonValue], placement["pose"])
        position = pose.get("position")
        if not isinstance(position, dict) or set(position) != {"x", "y", "z"}:
            raise PolicyError("Deployment seed requires XYZ model positions.")
        position["x"] = _number(_number(position["x"]) + dx)
        position["y"] = _number(_number(position["y"]) + dy)
        position["z"] = _number(position["z"])
    return proposal


@dataclass(frozen=True, slots=True, init=False)
class DeploymentCandidateSet:
    """Immutable proposals only: no engine state, legal mask or checkpoint metadata.

    Translations preserve the supplied formation, height and facing. They neither
    solve deployment nor guarantee any legal alternative. Duplicate resulting
    geometry consumes raw budget but is retained only at its first occurrence.
    """

    candidates: tuple[DeploymentPlacementCandidate, ...]
    _payload_json: str

    def __init__(self) -> None:
        raise PolicyError("Generate a deployment set from an actor-bound seed.")

    @classmethod
    def generate(
        cls,
        seed: DeploymentPlacementCandidate,
        *,
        context: PlayerDecisionContext,
        translations: tuple[tuple[float, float], ...] = DEFAULT_TRANSLATIONS,
        raw_budget: int = 64,
    ) -> DeploymentCandidateSet:
        if type(seed) is not DeploymentPlacementCandidate:
            raise PolicyError("Deployment generation requires a typed seed candidate.")
        seed.select(context)
        require_budget(raw_budget, maximum=64)
        if type(translations) is not tuple or len(translations) > 64:
            raise PolicyError("Deployment translations must be a tuple of at most 64 offsets.")
        offsets: list[list[float]] = []
        for offset in translations:
            if type(offset) is not tuple or len(offset) != 2:
                raise PolicyError("Deployment translations require XY pairs.")
            offsets.append([_number(offset[0]), _number(offset[1])])
        candidates: list[DeploymentPlacementCandidate] = []
        seen: set[str] = set()
        duplicates = 0
        for dx, dy in offsets[:raw_budget]:
            proposal = _translated(seed.to_payload()["proposal"], dx, dy)
            candidate = DeploymentPlacementCandidate.from_action(
                context.propose(proposal), context=context
            )
            if candidate.candidate_id in seen:
                duplicates += 1
            else:
                seen.add(candidate.candidate_id)
                candidates.append(candidate)
        attempted = min(len(offsets), raw_budget)
        stop = (
            DeploymentSearchStop.RAW_BUDGET
            if attempted < len(offsets)
            else DeploymentSearchStop.COMPLETE
        )
        if not candidates:
            raise DeploymentCandidateExhaustedError(
                stop_reason=stop, raw_attempts=attempted, duplicates=duplicates
            )
        payload = {
            "schema_version": DEPLOYMENT_SET_SCHEMA,
            "generator_id": DEPLOYMENT_GENERATOR,
            "seed": seed.to_payload(),
            "translations": offsets,
            "raw_budget": raw_budget,
            "raw_attempts": attempted,
            "duplicates": duplicates,
            "stop_reason": stop.value,
            "candidates": [candidate.to_payload() for candidate in candidates],
        }
        result = object.__new__(cls)
        object.__setattr__(result, "candidates", tuple(candidates))
        object.__setattr__(result, "_payload_json", canonical_json(payload))
        return result

    @property
    def content_hash(self) -> str:
        return payload_digest(self.to_payload())

    def to_payload(self) -> dict[str, JsonValue]:
        return cast(dict[str, JsonValue], json.loads(self._payload_json))

    def require_context(self, context: PlayerDecisionContext) -> None:
        for candidate in self.candidates:
            candidate.select(context)

    @classmethod
    def from_payload(
        cls, payload: object, *, context: PlayerDecisionContext
    ) -> DeploymentCandidateSet:
        if not isinstance(payload, dict):
            raise PolicyError("Deployment candidate set must be an object.")
        value = cast(dict[str, object], payload)
        if value.keys() != {
            "schema_version",
            "generator_id",
            "seed",
            "translations",
            "raw_budget",
            "raw_attempts",
            "duplicates",
            "stop_reason",
            "candidates",
        }:
            raise PolicyError("Deployment candidate set has missing or unknown fields.")
        offsets = value["translations"]
        if not isinstance(offsets, list) or any(
            not isinstance(offset, list) or len(cast(list[object], offset)) != 2
            for offset in cast(list[object], offsets)
        ):
            raise PolicyError("Deployment translations require a list of XY pairs.")
        expected = cls.generate(
            DeploymentPlacementCandidate.from_payload(value["seed"], context=context),
            context=context,
            translations=tuple(
                (_number(offset[0]), _number(offset[1]))
                for offset in cast(list[list[object]], offsets)
            ),
            raw_budget=require_budget(value["raw_budget"], maximum=64),
        )
        try:
            observed = canonical_json(validate_json_value(value))
        except EventLogError as exc:
            raise PolicyError("Deployment candidate set must be JSON-safe.") from exc
        if observed != expected._payload_json:
            raise PolicyError("Deployment candidate set or generation evidence drifted.")
        return expected
