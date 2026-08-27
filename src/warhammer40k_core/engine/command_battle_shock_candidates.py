from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Self, TypedDict, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.battle_shock import (
    BattleShockTestReason,
    BattleShockTestRequest,
)
from warhammer40k_core.engine.battle_shock_hooks import (
    BattleShockForcedTestApplication,
    BattleShockForcedTestApplicationPayload,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import (
    placed_alive_rules_unit_views,
    rules_unit_is_battle_shocked,
)
from warhammer40k_core.engine.unit_state import (
    BelowHalfStrengthContext,
    BelowHalfStrengthContextPayload,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


class CommandBattleShockCandidatePayload(TypedDict):
    unit_instance_id: str
    placed_alive_model_instance_ids: list[str]
    is_battle_shocked: bool
    forced_below_starting_strength: bool
    forced_test_applications: list[BattleShockForcedTestApplicationPayload]
    below_half_strength_context: BelowHalfStrengthContextPayload


@dataclass(frozen=True, slots=True)
class CommandBattleShockCandidate:
    """Immutable step-start predicate inventory for one placed, living rules unit."""

    unit_instance_id: str
    placed_alive_model_instance_ids: tuple[str, ...]
    is_battle_shocked: bool
    forced_below_starting_strength: bool
    below_half_strength_context: BelowHalfStrengthContext
    forced_test_applications: tuple[BattleShockForcedTestApplication, ...] = ()

    def __post_init__(self) -> None:
        unit_id = _validate_identifier("Command Battle-shock candidate unit", self.unit_instance_id)
        model_ids = _validate_identifier_tuple(
            "Command Battle-shock candidate placed models",
            self.placed_alive_model_instance_ids,
        )
        if not model_ids or model_ids != tuple(sorted(model_ids)):
            raise GameLifecycleError(
                "Command Battle-shock candidate placed models must be non-empty and sorted."
            )
        if type(self.is_battle_shocked) is not bool:
            raise GameLifecycleError("Command Battle-shock candidate shocked flag must be bool.")
        if type(self.forced_below_starting_strength) is not bool:
            raise GameLifecycleError("Command Battle-shock candidate forced flag must be bool.")
        applications = _validate_candidate_forced_test_applications(
            self.forced_test_applications,
            unit_instance_id=unit_id,
        )
        if self.forced_below_starting_strength != bool(applications):
            raise GameLifecycleError("Command Battle-shock candidate forced authority drifted.")
        context = self.below_half_strength_context
        if type(context) is not BelowHalfStrengthContext:
            raise GameLifecycleError("Command Battle-shock candidate requires strength context.")
        if context.unit_instance_id != unit_id or context.current_model_count != len(model_ids):
            raise GameLifecycleError("Command Battle-shock candidate strength context drifted.")
        object.__setattr__(self, "unit_instance_id", unit_id)
        object.__setattr__(self, "placed_alive_model_instance_ids", model_ids)
        object.__setattr__(self, "forced_test_applications", applications)

    def to_payload(self) -> CommandBattleShockCandidatePayload:
        return {
            "unit_instance_id": self.unit_instance_id,
            "placed_alive_model_instance_ids": list(self.placed_alive_model_instance_ids),
            "is_battle_shocked": self.is_battle_shocked,
            "forced_below_starting_strength": self.forced_below_starting_strength,
            "forced_test_applications": [
                application.to_payload() for application in self.forced_test_applications
            ],
            "below_half_strength_context": self.below_half_strength_context.to_payload(),
        }

    @classmethod
    def from_payload(cls, payload: CommandBattleShockCandidatePayload) -> Self:
        candidate = cls(
            unit_instance_id=payload["unit_instance_id"],
            placed_alive_model_instance_ids=tuple(payload["placed_alive_model_instance_ids"]),
            is_battle_shocked=payload["is_battle_shocked"],
            forced_below_starting_strength=payload["forced_below_starting_strength"],
            below_half_strength_context=BelowHalfStrengthContext.from_payload(
                payload["below_half_strength_context"]
            ),
            forced_test_applications=tuple(
                BattleShockForcedTestApplication.from_payload(application)
                for application in payload["forced_test_applications"]
            ),
        )
        if payload != candidate.to_payload():
            raise GameLifecycleError("Command Battle-shock candidate payload drifted.")
        return candidate


def command_battle_shock_candidate_inventory(
    state: GameState,
    active_player_id: str,
    forced_test_applications: tuple[BattleShockForcedTestApplication, ...],
) -> tuple[CommandBattleShockCandidate, ...]:
    """Capture every placed, living active-player rules unit at step entry."""
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Command Battle-shock candidates require GameState.")
    player_id = _validate_identifier("active_player_id", active_player_id)
    if player_id not in state.player_ids:
        raise GameLifecycleError("Command Battle-shock candidate player is not in this game.")
    applications = _validate_forced_test_applications(forced_test_applications)
    forced_by_unit_id = _forced_test_applications_by_unit_id(applications)
    forced_ids = set(forced_by_unit_id)
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Command Battle-shock candidates require battlefield state.")
    placed_ids = set(battlefield.placed_model_ids())
    candidates: list[CommandBattleShockCandidate] = []
    for rules_unit in placed_alive_rules_unit_views(state=state):
        if rules_unit.owner_player_id != player_id:
            continue
        model_ids = tuple(
            sorted(
                model.model_instance_id
                for model in rules_unit.alive_models()
                if model.model_instance_id in placed_ids
            )
        )
        context = BelowHalfStrengthContext.from_rules_unit(
            rules_unit=rules_unit,
            starting_strength=state.starting_strength_record_for_unit(rules_unit.unit_instance_id),
            current_model_ids=model_ids,
        )
        candidates.append(
            CommandBattleShockCandidate(
                unit_instance_id=rules_unit.unit_instance_id,
                placed_alive_model_instance_ids=model_ids,
                is_battle_shocked=rules_unit_is_battle_shocked(
                    state=state,
                    unit_instance_id=rules_unit.unit_instance_id,
                ),
                forced_below_starting_strength=rules_unit.unit_instance_id in forced_ids,
                below_half_strength_context=context,
                forced_test_applications=forced_by_unit_id.get(
                    rules_unit.unit_instance_id,
                    (),
                ),
            )
        )
    inventory = tuple(sorted(candidates, key=lambda candidate: candidate.unit_instance_id))
    if forced_ids - {candidate.unit_instance_id for candidate in inventory}:
        raise GameLifecycleError("Command Battle-shock forced-test target is not a candidate.")
    return inventory


def validate_command_battle_shock_candidate_inventory(
    values: object,
    *,
    active_player_id: str,
    phase_start_battle_shocked_unit_ids: tuple[str, ...],
    required_test_requests: tuple[BattleShockTestRequest, ...],
) -> tuple[CommandBattleShockCandidate, ...]:
    if type(values) is not tuple or any(
        type(value) is not CommandBattleShockCandidate for value in cast(tuple[object, ...], values)
    ):
        raise GameLifecycleError("Command Battle-shock candidates must be a typed tuple.")
    candidates = cast(tuple[CommandBattleShockCandidate, ...], values)
    if candidates != tuple(sorted(candidates, key=lambda candidate: candidate.unit_instance_id)):
        raise GameLifecycleError("Command Battle-shock candidates must be deterministic.")
    candidate_ids = tuple(candidate.unit_instance_id for candidate in candidates)
    if len(set(candidate_ids)) != len(candidate_ids):
        raise GameLifecycleError("Command Battle-shock candidate unit IDs must be unique.")
    player_id = _validate_identifier("active_player_id", active_player_id)
    if any(
        candidate.below_half_strength_context.player_id != player_id for candidate in candidates
    ):
        raise GameLifecycleError("Command Battle-shock candidate player drifted.")
    shocked_ids = tuple(
        candidate.unit_instance_id for candidate in candidates if candidate.is_battle_shocked
    )
    if phase_start_battle_shocked_unit_ids != shocked_ids:
        raise GameLifecycleError("Command Battle-shock phase-start inventory drifted.")
    expected: dict[str, tuple[BattleShockTestReason, BelowHalfStrengthContext]] = {}
    for candidate in candidates:
        context = candidate.below_half_strength_context
        if candidate.forced_below_starting_strength and context.is_below_starting_strength:
            expected[candidate.unit_instance_id] = (
                BattleShockTestReason.BELOW_STARTING_STRENGTH_FORCED,
                context,
            )
        elif candidate.is_battle_shocked or context.is_at_or_below_half_strength:
            expected[candidate.unit_instance_id] = (
                BattleShockTestReason.COMMAND_PHASE_REQUIRED,
                context,
            )
    actual = {
        request.unit_instance_id: (request.reason, request.below_half_strength_context)
        for request in required_test_requests
    }
    if actual != expected:
        raise GameLifecycleError("Command Battle-shock required tests omit candidate authority.")
    return candidates


def validate_command_battle_shock_step_progress(
    *,
    battle_shock_step_started: bool,
    command_points_granted: bool,
    battle_shock_step_resolved: bool,
    phase_start_unit_ids: tuple[str, ...],
    candidate_inventory: tuple[CommandBattleShockCandidate, ...],
    required_test_requests: tuple[BattleShockTestRequest, ...],
    completed_test_request_ids: tuple[str, ...],
) -> None:
    """Validate the immutable Command Battle-shock snapshot and completion prefix."""

    if battle_shock_step_started and not command_points_granted:
        raise GameLifecycleError(
            "CommandStepState cannot enter Battle-shock before Command step CP gain."
        )
    if not battle_shock_step_started:
        if battle_shock_step_resolved:
            raise GameLifecycleError(
                "CommandStepState resolved Battle-shock state must be in Battle-shock step."
            )
        if (
            phase_start_unit_ids
            or candidate_inventory
            or required_test_requests
            or completed_test_request_ids
        ):
            raise GameLifecycleError(
                "CommandStepState cannot retain Battle-shock snapshot or progress before its step."
            )
        return
    required_request_ids = tuple(request.request_id for request in required_test_requests)
    if completed_test_request_ids != required_request_ids[: len(completed_test_request_ids)]:
        raise GameLifecycleError(
            "CommandStepState completed Battle-shock requests must be an exact prefix."
        )
    if battle_shock_step_resolved and completed_test_request_ids != required_request_ids:
        raise GameLifecycleError(
            "CommandStepState cannot resolve before all required Battle-shock tests."
        )


_validate_identifier = IdentifierValidator(GameLifecycleError)


def _validate_identifier_tuple(field_name: str, values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    identifiers = tuple(
        _validate_identifier(f"{field_name} value", value)
        for value in cast(tuple[object, ...], values)
    )
    if len(set(identifiers)) != len(identifiers):
        raise GameLifecycleError(f"{field_name} must not contain duplicates.")
    return identifiers


def forced_test_unit_ids(
    applications: tuple[BattleShockForcedTestApplication, ...],
) -> tuple[str, ...]:
    validated = _validate_forced_test_applications(applications)
    return tuple(
        sorted({unit_id for application in validated for unit_id in application.unit_instance_ids})
    )


def forced_test_applications_from_candidate_inventory(
    candidates: tuple[CommandBattleShockCandidate, ...],
) -> tuple[BattleShockForcedTestApplication, ...]:
    if type(candidates) is not tuple or any(
        type(candidate) is not CommandBattleShockCandidate
        for candidate in cast(tuple[object, ...], candidates)
    ):
        raise GameLifecycleError("Command Battle-shock candidate inventory must be typed.")
    grouped: dict[tuple[str, str], list[str]] = {}
    for candidate in candidates:
        for application in candidate.forced_test_applications:
            grouped.setdefault((application.hook_id, application.source_id), []).append(
                candidate.unit_instance_id
            )
    return tuple(
        BattleShockForcedTestApplication(
            hook_id=hook_id,
            source_id=source_id,
            unit_instance_ids=tuple(unit_ids),
        )
        for (hook_id, source_id), unit_ids in sorted(grouped.items())
    )


def _validate_forced_test_applications(
    values: object,
) -> tuple[BattleShockForcedTestApplication, ...]:
    if type(values) is not tuple or any(
        type(value) is not BattleShockForcedTestApplication
        for value in cast(tuple[object, ...], values)
    ):
        raise GameLifecycleError("Command Battle-shock forced-test applications must be typed.")
    applications = cast(tuple[BattleShockForcedTestApplication, ...], values)
    expected = tuple(
        sorted(applications, key=lambda application: (application.hook_id, application.source_id))
    )
    if applications != expected or len(
        {(application.hook_id, application.source_id) for application in applications}
    ) != len(applications):
        raise GameLifecycleError("Command Battle-shock forced-test applications are ambiguous.")
    return applications


def _forced_test_applications_by_unit_id(
    applications: tuple[BattleShockForcedTestApplication, ...],
) -> dict[str, tuple[BattleShockForcedTestApplication, ...]]:
    grouped: dict[str, list[BattleShockForcedTestApplication]] = {}
    for application in applications:
        for unit_id in application.unit_instance_ids:
            grouped.setdefault(unit_id, []).append(
                BattleShockForcedTestApplication(
                    hook_id=application.hook_id,
                    source_id=application.source_id,
                    unit_instance_ids=(unit_id,),
                )
            )
    return {unit_id: tuple(values) for unit_id, values in grouped.items()}


def _validate_candidate_forced_test_applications(
    values: object,
    *,
    unit_instance_id: str,
) -> tuple[BattleShockForcedTestApplication, ...]:
    applications = _validate_forced_test_applications(values)
    if any(application.unit_instance_ids != (unit_instance_id,) for application in applications):
        raise GameLifecycleError("Command Battle-shock candidate forced target drifted.")
    return applications


__all__ = (
    "CommandBattleShockCandidate",
    "CommandBattleShockCandidatePayload",
    "command_battle_shock_candidate_inventory",
    "forced_test_applications_from_candidate_inventory",
    "forced_test_unit_ids",
    "validate_command_battle_shock_candidate_inventory",
    "validate_command_battle_shock_step_progress",
)
