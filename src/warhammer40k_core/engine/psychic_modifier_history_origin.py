"""Authenticate completed Psychic history from independent pre-declaration inputs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.attack_sequence_psychic_modifiers import DECISION_TYPE
from warhammer40k_core.engine.event_log import JsonValue, canonical_json, validate_json_value
from warhammer40k_core.engine.fight_resolution import SUBMIT_MELEE_DECLARATION_DECISION_TYPE
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.weapon_declaration import SUBMIT_SHOOTING_DECLARATION_DECISION_TYPE

if TYPE_CHECKING:
    from warhammer40k_core.engine.decision_request import DecisionRequest
    from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload

ORIGIN_KEY = "psychic_modifier_history_origin"
_DECLARATIONS = frozenset(
    {SUBMIT_SHOOTING_DECLARATION_DECISION_TYPE, SUBMIT_MELEE_DECLARATION_DECISION_TYPE}
)


@dataclass(frozen=True, slots=True)
class PsychicModifierHistoryOrigin:
    """One immutable, operator-only root; never a copy of modifier-choice claims.

    Retaining the first declaration boundary also covers later attacks and effects
    that have expired by restoration. Origins cannot contain another origin or a
    completed declaration prefix. Replay therefore terminates at independently
    validated pre-attack state, rather than trusting a captured Psychic prefix.
    """

    initial_lifecycle_json: str

    def to_payload(self) -> dict[str, JsonValue]:
        import json

        value = validate_json_value(json.loads(self.initial_lifecycle_json))
        if not isinstance(value, dict):
            raise GameLifecycleError("Psychic historical origin must be a lifecycle object.")
        return value

    @classmethod
    def from_payload(cls, payload: JsonValue) -> PsychicModifierHistoryOrigin:
        from warhammer40k_core.engine.decision_controller import (
            DecisionController,
            DecisionControllerPayload,
        )

        if not isinstance(payload, dict) or ORIGIN_KEY in payload:
            raise GameLifecycleError("Psychic historical origin must not contain another origin.")
        raw_decisions = payload.get("decisions")
        if not isinstance(raw_decisions, dict):
            raise GameLifecycleError("Psychic historical origin lacks decision authority.")
        decisions = DecisionController.from_payload(cast(DecisionControllerPayload, raw_decisions))
        if any(
            record.request.decision_type in _DECLARATIONS | {DECISION_TYPE}
            for record in decisions.records
        ):
            raise GameLifecycleError(
                "Psychic historical origin must precede the first declaration."
            )
        if (
            not decisions.queue.pending_requests
            or decisions.queue.pending_requests[0].decision_type not in _DECLARATIONS
        ):
            raise GameLifecycleError("Psychic historical origin requires a pending declaration.")
        return cls(canonical_json(payload))


def capture_psychic_history_origin(
    *,
    lifecycle: GameLifecycle,
    request: DecisionRequest | None,
    existing: PsychicModifierHistoryOrigin | None,
) -> PsychicModifierHistoryOrigin | None:
    if existing is not None or request is None or request.decision_type not in _DECLARATIONS:
        return existing
    # The immutable JSON copy is prepared before queue pop and installed only after
    # submit_result accepts the result. Invalid submissions cannot change authority.
    payload = validate_json_value(lifecycle.to_payload())
    if not isinstance(payload, dict):
        raise GameLifecycleError("Psychic historical origin requires a lifecycle object.")
    return PsychicModifierHistoryOrigin.from_payload(payload)


def validate_psychic_history_origin(
    *, lifecycle: GameLifecycle, origin: PsychicModifierHistoryOrigin | None
) -> None:
    from warhammer40k_core.engine.replay import ReplayArtifact, ReplayRunner

    decisions = lifecycle.decision_controller
    if not any(record.request.decision_type == DECISION_TYPE for record in decisions.records):
        return
    if origin is None:
        raise GameLifecycleError("Completed Psychic history lacks its historical attack origin.")
    payload = origin.to_payload()
    current = lifecycle.to_payload()
    if canonical_json(payload.get("config")) != canonical_json(current["config"]):
        raise GameLifecycleError("Psychic historical origin catalog/config authority drift.")
    original_decisions = payload["decisions"]
    if not isinstance(original_decisions, dict):
        raise GameLifecycleError("Psychic historical origin lacks decision authority.")
    current_decisions = validate_json_value(current["decisions"])
    if not isinstance(current_decisions, dict):
        raise GameLifecycleError("Psychic historical current ledger must be an object.")
    for key in ("records", "event_log"):
        prefix = original_decisions[key]
        if not isinstance(prefix, list):
            raise GameLifecycleError("Psychic historical origin ledger must be a list.")
        actual = current_decisions[key]
        if not isinstance(actual, list) or canonical_json(prefix) != canonical_json(
            actual[: len(prefix)]
        ):
            raise GameLifecycleError("Psychic historical origin ledger prefix drift.")
    artifact = ReplayArtifact.capture(
        artifact_id="psychic-modifier-historical-authority",
        initial_lifecycle_payload=cast("GameLifecyclePayload", payload),
        final_lifecycle=lifecycle,
    )
    result = ReplayRunner(artifact).run()
    if not result.reproduced_exactly:
        raise GameLifecycleError(
            "Psychic historical attack source reconstruction drifted: "
            + ", ".join(diagnostic.diagnostic_code.value for diagnostic in result.diagnostics)
        )
