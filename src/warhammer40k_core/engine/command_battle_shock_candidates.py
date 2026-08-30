from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
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
    rules_unit_is_battle_shocked,
    rules_unit_views_from_armies,
)
from warhammer40k_core.engine.unit_state import (
    BelowHalfStrengthContext,
    BelowHalfStrengthContextPayload,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


class CommandBattleShockCandidatePayload(TypedDict):
    unit_instance_id: str
    component_unit_instance_ids: list[str]
    is_battle_shocked: bool
    eligibility_reasons: list[str]
    forced_test_applications: list[BattleShockForcedTestApplicationPayload]
    below_half_strength_context: BelowHalfStrengthContextPayload


class CommandBattleShockEligibilityReason(StrEnum):
    CURRENTLY_BATTLE_SHOCKED = "currently_battle_shocked"
    AT_OR_BELOW_HALF_STRENGTH = "at_or_below_half_strength"
    BELOW_STARTING_STRENGTH_FORCED = "below_starting_strength_forced"


_ELIGIBILITY_REASON_ORDER = {
    reason: index for index, reason in enumerate(CommandBattleShockEligibilityReason)
}


@dataclass(frozen=True, slots=True)
class CommandBattleShockCandidate:
    """Immutable step-start eligibility inventory for one living rules unit."""

    unit_instance_id: str
    component_unit_instance_ids: tuple[str, ...]
    is_battle_shocked: bool
    below_half_strength_context: BelowHalfStrengthContext
    eligibility_reasons: tuple[CommandBattleShockEligibilityReason, ...] = ()
    forced_test_applications: tuple[BattleShockForcedTestApplication, ...] = ()

    def __post_init__(self) -> None:
        unit_id = _validate_identifier("Command Battle-shock candidate unit", self.unit_instance_id)
        component_ids = _validate_identifier_tuple(
            "Command Battle-shock candidate component units",
            self.component_unit_instance_ids,
        )
        if not component_ids or component_ids != tuple(sorted(component_ids)):
            raise GameLifecycleError(
                "Command Battle-shock candidate component units must be non-empty and sorted."
            )
        if type(self.is_battle_shocked) is not bool:
            raise GameLifecycleError("Command Battle-shock candidate shocked flag must be bool.")
        reasons = _validate_eligibility_reasons(self.eligibility_reasons)
        applications = _validate_candidate_forced_test_applications(
            self.forced_test_applications,
            unit_instance_id=unit_id,
        )
        context = self.below_half_strength_context
        if type(context) is not BelowHalfStrengthContext:
            raise GameLifecycleError("Command Battle-shock candidate requires strength context.")
        if context.unit_instance_id != unit_id or context.current_model_count < 1:
            raise GameLifecycleError("Command Battle-shock candidate strength context drifted.")
        expected_reasons = _candidate_eligibility_reasons(
            is_battle_shocked=self.is_battle_shocked,
            context=context,
            forced_test_applications=applications,
        )
        if reasons != expected_reasons:
            raise GameLifecycleError("Command Battle-shock candidate eligibility drifted.")
        object.__setattr__(self, "unit_instance_id", unit_id)
        object.__setattr__(self, "component_unit_instance_ids", component_ids)
        object.__setattr__(self, "eligibility_reasons", reasons)
        object.__setattr__(self, "forced_test_applications", applications)

    @property
    def test_reason(self) -> BattleShockTestReason | None:
        if (
            CommandBattleShockEligibilityReason.BELOW_STARTING_STRENGTH_FORCED
            in self.eligibility_reasons
        ):
            return BattleShockTestReason.BELOW_STARTING_STRENGTH_FORCED
        if self.eligibility_reasons:
            return BattleShockTestReason.COMMAND_PHASE_REQUIRED
        return None

    def to_payload(self) -> CommandBattleShockCandidatePayload:
        return {
            "unit_instance_id": self.unit_instance_id,
            "component_unit_instance_ids": list(self.component_unit_instance_ids),
            "is_battle_shocked": self.is_battle_shocked,
            "eligibility_reasons": [reason.value for reason in self.eligibility_reasons],
            "forced_test_applications": [
                application.to_payload() for application in self.forced_test_applications
            ],
            "below_half_strength_context": self.below_half_strength_context.to_payload(),
        }

    @classmethod
    def from_payload(cls, payload: CommandBattleShockCandidatePayload) -> Self:
        candidate = cls(
            unit_instance_id=payload["unit_instance_id"],
            component_unit_instance_ids=tuple(payload["component_unit_instance_ids"]),
            is_battle_shocked=payload["is_battle_shocked"],
            below_half_strength_context=BelowHalfStrengthContext.from_payload(
                payload["below_half_strength_context"]
            ),
            eligibility_reasons=tuple(
                command_battle_shock_eligibility_reason_from_token(reason)
                for reason in payload["eligibility_reasons"]
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
    """Capture every living active-player canonical rules unit at step entry."""
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Command Battle-shock candidates require GameState.")
    player_id = _validate_identifier("active_player_id", active_player_id)
    if player_id not in state.player_ids:
        raise GameLifecycleError("Command Battle-shock candidate player is not in this game.")
    applications = _validate_forced_test_applications(forced_test_applications)
    forced_by_unit_id = _forced_test_applications_by_unit_id(applications)
    forced_ids = set(forced_by_unit_id)
    candidates: list[CommandBattleShockCandidate] = []
    for rules_unit in rules_unit_views_from_armies(armies=tuple(state.army_definitions)):
        if rules_unit.owner_player_id != player_id:
            continue
        model_ids = tuple(sorted(model.model_instance_id for model in rules_unit.alive_models()))
        if not model_ids:
            continue
        context = BelowHalfStrengthContext.from_rules_unit(
            rules_unit=rules_unit,
            starting_strength=state.starting_strength_record_for_unit(rules_unit.unit_instance_id),
            current_model_ids=model_ids,
        )
        applications_for_unit = forced_by_unit_id.get(rules_unit.unit_instance_id, ())
        is_battle_shocked = rules_unit_is_battle_shocked(
            state=state,
            unit_instance_id=rules_unit.unit_instance_id,
        )
        candidates.append(
            CommandBattleShockCandidate(
                unit_instance_id=rules_unit.unit_instance_id,
                component_unit_instance_ids=tuple(sorted(rules_unit.component_unit_instance_ids)),
                is_battle_shocked=is_battle_shocked,
                below_half_strength_context=context,
                eligibility_reasons=_candidate_eligibility_reasons(
                    is_battle_shocked=is_battle_shocked,
                    context=context,
                    forced_test_applications=applications_for_unit,
                ),
                forced_test_applications=applications_for_unit,
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
    return candidates


def validate_command_battle_shock_step_progress(
    *,
    battle_shock_step_started: bool,
    command_points_granted: bool,
    battle_shock_step_resolved: bool,
    phase_start_unit_ids: tuple[str, ...],
    candidate_inventory: tuple[CommandBattleShockCandidate, ...],
    candidate_order_unit_ids: tuple[str, ...],
    in_flight_test_request: BattleShockTestRequest | None,
    completed_test_request_ids: tuple[str, ...],
    battle_round: int,
    active_player_id: str,
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
            or candidate_order_unit_ids
            or in_flight_test_request is not None
            or completed_test_request_ids
        ):
            raise GameLifecycleError(
                "CommandStepState cannot retain Battle-shock snapshot or progress before its step."
            )
        return
    required_candidates = tuple(
        candidate for candidate in candidate_inventory if candidate.test_reason is not None
    )
    required_unit_ids = {candidate.unit_instance_id for candidate in required_candidates}
    if candidate_order_unit_ids and (
        not set(candidate_order_unit_ids).issubset(required_unit_ids)
        or len(candidate_order_unit_ids) != len(set(candidate_order_unit_ids))
    ):
        raise GameLifecycleError(
            "CommandStepState Battle-shock candidate order must be a unique required-unit prefix."
        )
    if (completed_test_request_ids or in_flight_test_request is not None) and not (
        candidate_order_unit_ids
    ):
        raise GameLifecycleError(
            "CommandStepState cannot progress before Battle-shock candidate order resolves."
        )
    completed_count = len(completed_test_request_ids)
    if len(candidate_order_unit_ids) not in {completed_count, completed_count + 1}:
        raise GameLifecycleError(
            "CommandStepState Battle-shock candidate sequencing order may contain only the "
            "completed prefix and one selected in-flight candidate."
        )
    candidate_by_id = {candidate.unit_instance_id: candidate for candidate in required_candidates}
    required_request_ids = tuple(
        command_battle_shock_request_id(
            battle_round=battle_round,
            active_player_id=active_player_id,
            unit_instance_id=unit_id,
            reason=cast(BattleShockTestReason, candidate_by_id[unit_id].test_reason),
        )
        for unit_id in candidate_order_unit_ids
    )
    if completed_test_request_ids != required_request_ids[: len(completed_test_request_ids)]:
        raise GameLifecycleError(
            "CommandStepState completed Battle-shock requests must be an exact prefix."
        )
    if in_flight_test_request is not None:
        if completed_count >= len(candidate_order_unit_ids):
            raise GameLifecycleError("CommandStepState Battle-shock in-flight request is excess.")
        next_unit_id = candidate_order_unit_ids[len(completed_test_request_ids)]
        next_candidate = candidate_by_id[next_unit_id]
        if (
            in_flight_test_request.request_id
            != required_request_ids[len(completed_test_request_ids)]
            or in_flight_test_request.unit_instance_id != next_unit_id
            or in_flight_test_request.reason is not next_candidate.test_reason
        ):
            raise GameLifecycleError("CommandStepState Battle-shock in-flight request drifted.")
    if battle_shock_step_resolved and (
        set(candidate_order_unit_ids) != required_unit_ids
        or len(candidate_order_unit_ids) != len(required_unit_ids)
        or completed_test_request_ids != required_request_ids
    ):
        raise GameLifecycleError(
            "CommandStepState cannot resolve before all required Battle-shock tests."
        )
    if battle_shock_step_resolved and in_flight_test_request is not None:
        raise GameLifecycleError("CommandStepState resolved with an in-flight Battle-shock test.")


def command_battle_shock_request_id(
    *,
    battle_round: int,
    active_player_id: str,
    unit_instance_id: str,
    reason: BattleShockTestReason,
) -> str:
    if type(battle_round) is not int or battle_round < 1:
        raise GameLifecycleError("Command Battle-shock request battle round is invalid.")
    player_id = _validate_identifier("active_player_id", active_player_id)
    unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    if type(reason) is not BattleShockTestReason:
        raise GameLifecycleError("Command Battle-shock request reason is invalid.")
    return f"battle-shock:{battle_round:02d}:{player_id}:{unit_id}:{reason.value}"


def command_battle_shock_eligibility_reason_from_token(
    token: object,
) -> CommandBattleShockEligibilityReason:
    if type(token) is CommandBattleShockEligibilityReason:
        return token
    if type(token) is not str:
        raise GameLifecycleError("Command Battle-shock eligibility reason must be a string.")
    try:
        return CommandBattleShockEligibilityReason(token)
    except ValueError as exc:
        raise GameLifecycleError(
            f"Unsupported Command Battle-shock eligibility reason: {token}."
        ) from exc


def _validate_eligibility_reasons(
    values: object,
) -> tuple[CommandBattleShockEligibilityReason, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("Command Battle-shock eligibility reasons must be a tuple.")
    reasons = tuple(
        command_battle_shock_eligibility_reason_from_token(value)
        for value in cast(tuple[object, ...], values)
    )
    expected = tuple(sorted(set(reasons), key=_ELIGIBILITY_REASON_ORDER.__getitem__))
    if reasons != expected:
        raise GameLifecycleError(
            "Command Battle-shock eligibility reasons must be deterministic and unique."
        )
    return reasons


def _candidate_eligibility_reasons(
    *,
    is_battle_shocked: bool,
    context: BelowHalfStrengthContext,
    forced_test_applications: tuple[BattleShockForcedTestApplication, ...],
) -> tuple[CommandBattleShockEligibilityReason, ...]:
    reasons: list[CommandBattleShockEligibilityReason] = []
    if is_battle_shocked:
        reasons.append(CommandBattleShockEligibilityReason.CURRENTLY_BATTLE_SHOCKED)
    if context.is_at_or_below_half_strength:
        reasons.append(CommandBattleShockEligibilityReason.AT_OR_BELOW_HALF_STRENGTH)
    if forced_test_applications:
        if not context.is_below_starting_strength:
            raise GameLifecycleError(
                "Command Battle-shock forced candidate is not below Starting Strength."
            )
        reasons.append(CommandBattleShockEligibilityReason.BELOW_STARTING_STRENGTH_FORCED)
    return tuple(reasons)


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
    "CommandBattleShockEligibilityReason",
    "command_battle_shock_candidate_inventory",
    "command_battle_shock_eligibility_reason_from_token",
    "command_battle_shock_request_id",
    "forced_test_applications_from_candidate_inventory",
    "forced_test_unit_ids",
    "validate_command_battle_shock_candidate_inventory",
    "validate_command_battle_shock_step_progress",
)
