"""A source-backed commitment window before a selected unit chooses a grant."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from warhammer40k_core.core.dice import DiceExpression, DiceRollSpec
from warhammer40k_core.core.modified_dice import ModifiedRollResult, UnmodifiedRollResult
from warhammer40k_core.engine.catalog_selected_target_test_modifiers import (
    LEADERSHIP_TEST_ROLL_TYPE,
    selected_target_test_roll_modifiers,
)
from warhammer40k_core.engine.damage_allocation import (
    MortalWoundApplicationProgress,
    MortalWoundRoutingResult,
    continue_mortal_wound_application,
)
from warhammer40k_core.engine.decision import DiceRollManager
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.destruction_provenance import DestructionSourceKind
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.mortal_wound_destruction_evidence import (
    MortalWoundDestructionEvidence,
)
from warhammer40k_core.engine.mortal_wound_model_allocation import resolve_mortal_wound_decision
from warhammer40k_core.engine.nonattack_modifier_evaluation import evaluate_leadership_modifiers
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

if TYPE_CHECKING:
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.decision_result import DecisionResult
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.mortal_wound_feel_no_pain_hooks import (
        MortalWoundFeelNoPainContinuationContext,
    )
    from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry


PREPARATION_KEY = "unit_grant_preparation"
COMMITMENT_RESULT_KEY = "unit_grant_commitment_result_id"


@dataclass(frozen=True, slots=True)
class UnitGrantPreparation:
    source_rule_id: str
    label: str
    leadership_roll_type: str
    mortal_wounds_roll_type: str
    mortal_wound_source_kind: str
    resolved_event_type: str
    pending_event_type: str
    auto_pass: bool = False

    @property
    def option_id(self) -> str:
        return f"{self.source_rule_id}:commit"

    def to_payload(self) -> dict[str, JsonValue]:
        return {
            "source_rule_id": self.source_rule_id,
            "label": self.label,
            "leadership_roll_type": self.leadership_roll_type,
            "mortal_wounds_roll_type": self.mortal_wounds_roll_type,
            "mortal_wound_source_kind": self.mortal_wound_source_kind,
            "resolved_event_type": self.resolved_event_type,
            "pending_event_type": self.pending_event_type,
            "auto_pass": self.auto_pass,
        }

    @classmethod
    def from_payload(cls, payload: JsonValue) -> UnitGrantPreparation:
        if not isinstance(payload, dict) or type(payload.get("auto_pass")) is not bool:
            raise GameLifecycleError("Invalid unit grant preparation.")
        auto_pass = payload["auto_pass"]
        assert isinstance(auto_pass, bool)
        return cls(
            source_rule_id=_string(payload, "source_rule_id"),
            label=_string(payload, "label"),
            leadership_roll_type=_string(payload, "leadership_roll_type"),
            mortal_wounds_roll_type=_string(payload, "mortal_wounds_roll_type"),
            mortal_wound_source_kind=_string(payload, "mortal_wound_source_kind"),
            resolved_event_type=_string(payload, "resolved_event_type"),
            pending_event_type=_string(payload, "pending_event_type"),
            auto_pass=auto_pass,
        )


class _PreparedGrant(Protocol):
    @property
    def preparation(self) -> UnitGrantPreparation | None: ...


def preparation_for(grants: tuple[_PreparedGrant, ...]) -> UnitGrantPreparation | None:
    preparations = {grant.preparation for grant in grants if grant.preparation is not None}
    if len(preparations) > 1:
        raise GameLifecycleError("Selected unit grants have conflicting preparations.")
    return next(iter(preparations), None)


def commitment_request(
    *,
    state: GameState,
    decisions: DecisionController,
    decision_type: str,
    actor_id: str,
    phase: BattlePhase,
    unit_id: str,
    selection_request_id: str,
    selection_result_id: str,
    preparation: UnitGrantPreparation,
    decline_option_id: str,
) -> LifecycleStatus:
    payload: dict[str, JsonValue] = {
        "game_id": state.game_id,
        "battle_round": state.battle_round,
        "phase": phase.value,
        "unit_instance_id": unit_id,
        "selection_request_id": selection_request_id,
        "selection_result_id": selection_result_id,
        PREPARATION_KEY: preparation.to_payload(),
    }
    request = DecisionRequest(
        request_id=state.next_decision_request_id(),
        decision_type=decision_type,
        actor_id=actor_id,
        payload=payload,
        options=(
            DecisionOption(
                option_id=decline_option_id,
                label=f"Decline {preparation.label}",
                payload={**payload, "commit": False},
            ),
            DecisionOption(
                option_id=preparation.option_id,
                label=f"Make a {preparation.label}",
                payload={**payload, "commit": True},
            ),
        ),
    )
    decisions.request_decision(request)
    return LifecycleStatus.waiting_for_decision(
        stage=state.stage,
        decision_request=request,
        payload={"phase": phase.value, "decision_type": decision_type, **payload},
    )


def is_commitment_request(request: DecisionRequest) -> bool:
    return isinstance(request.payload, dict) and PREPARATION_KEY in request.payload


def validate_commitment(
    *,
    request: DecisionRequest,
    result: DecisionResult,
    preparation: UnitGrantPreparation | None,
    unit_id: str,
    selection_request_id: str,
    selection_result_id: str,
) -> None:
    payload = request.payload
    if (
        not isinstance(payload, dict)
        or preparation is None
        or payload.get(PREPARATION_KEY) != preparation.to_payload()
        or payload.get("unit_instance_id") != unit_id
        or payload.get("selection_request_id") != selection_request_id
        or payload.get("selection_result_id") != selection_result_id
        or result.payload
        != {**payload, "commit": result.selected_option_id == preparation.option_id}
    ):
        raise GameLifecycleError("Selected unit grant commitment context drifted.")


def commitment_record_result(decisions: DecisionController, result_id: str) -> DecisionResult:
    for record in reversed(decisions.records):
        if record.result.result_id == result_id and is_commitment_request(record.request):
            return record.result
    raise GameLifecycleError("Selected unit grant commitment record is missing.")


def resolve_commitment(
    *,
    state: GameState,
    decisions: DecisionController,
    runtime_modifier_registry: RuntimeModifierRegistry,
    result: DecisionResult,
    phase: BattlePhase,
) -> LifecycleStatus | None:
    request = decisions.record_for_result(result).request
    if not isinstance(request.payload, dict):
        raise GameLifecycleError("Selected unit grant commitment requires a payload.")
    preparation = UnitGrantPreparation.from_payload(request.payload[PREPARATION_KEY])
    if result.selected_option_id != preparation.option_id:
        raise GameLifecycleError("Selected unit grant preparation requires commitment.")
    unit = rules_unit_view_by_id(
        state=state, unit_instance_id=_string(request.payload, "unit_instance_id")
    )
    if unit.owner_player_id != result.actor_id:
        raise GameLifecycleError("Selected unit grant commitment owner drifted.")
    payload: dict[str, JsonValue] = {
        "game_id": state.game_id,
        "battle_round": state.battle_round,
        "phase": phase.value,
        "source_rule_id": preparation.source_rule_id,
        "player_id": unit.owner_player_id,
        "unit_instance_id": unit.unit_instance_id,
        "selection_request_id": request.payload["selection_request_id"],
        "selection_result_id": request.payload["selection_result_id"],
        "commitment_request_id": request.request_id,
        COMMITMENT_RESULT_KEY: result.result_id,
        "leadership_target": None,
        "leadership_roll": None,
        "leadership_modified_roll": None,
        "leadership_auto_pass": preparation.auto_pass,
        "passed": True,
        "d3_result": None,
        "mortal_wound_application": None,
    }
    if preparation.auto_pass:
        decisions.event_log.append(preparation.resolved_event_type, payload)
        return None
    evaluation = evaluate_leadership_modifiers(
        state=state,
        decisions=decisions,
        unit_instance_id=unit.unit_instance_id,
        occurrence_id=f"leadership-test:{result.result_id}",
        ability_index=runtime_modifier_registry.modifier_permission_index(unit.owner_player_id),
        runtime_modifier_registry=runtime_modifier_registry,
        roll_modifiers=selected_target_test_roll_modifiers(
            state=state,
            unit_instance_id=unit.unit_instance_id,
            roll_type=LEADERSHIP_TEST_ROLL_TYPE,
        ),
        source_context={
            "continuation": PREPARATION_KEY,
            "phase": phase.value,
            COMMITMENT_RESULT_KEY: result.result_id,
        },
    )
    if evaluation.pending_status is not None:
        return evaluation.pending_status
    dice = DiceRollManager(state.private_rng_seed, event_log=decisions.event_log)
    leadership_roll = dice.roll(
        DiceRollSpec(
            expression=DiceExpression(quantity=2, sides=6),
            reason=f"{preparation.label} Leadership test for {unit.unit_instance_id}",
            roll_type=preparation.leadership_roll_type,
            actor_id=unit.unit_instance_id,
        )
    )
    modified_roll = ModifiedRollResult.from_unmodified(
        UnmodifiedRollResult.from_state(leadership_roll), modifiers=evaluation.roll_modifiers
    )
    payload.update(
        leadership_target=evaluation.leadership_target,
        leadership_roll=validate_json_value(leadership_roll.to_payload()),
        leadership_modified_roll=validate_json_value(modified_roll.to_payload()),
        passed=modified_roll.final_value >= evaluation.leadership_target,
    )
    if payload["passed"] is True:
        decisions.event_log.append(preparation.resolved_event_type, payload)
        return None
    d3_result = dice.roll_d3(
        reason=f"{preparation.label} mortal wounds for {unit.unit_instance_id}",
        roll_type=preparation.mortal_wounds_roll_type,
        actor_id=unit.unit_instance_id,
    )
    payload["d3_result"] = validate_json_value(d3_result.to_payload())
    progress = MortalWoundApplicationProgress.start(
        application_id=f"{result.result_id}:{preparation.source_rule_id}:mortal-wounds",
        source_rule_id=preparation.source_rule_id,
        source_context={
            "source_kind": preparation.mortal_wound_source_kind,
            PREPARATION_KEY: preparation.to_payload(),
            "resolution_payload": payload,
        },
        target_unit_instance_id=unit.unit_instance_id,
        defender_player_id=unit.owner_player_id,
        mortal_wounds=d3_result.value,
        spill_over=True,
        destruction_evidence=MortalWoundDestructionEvidence.for_non_attack_state(
            state=state,
            destroying_player_id=unit.owner_player_id,
            source_rules_unit_instance_id=unit.unit_instance_id,
            source_model_instance_id=None,
            destruction_source_kind=DestructionSourceKind.ABILITY,
            action_phase=phase,
            source_step=preparation.mortal_wound_source_kind,
        ),
    )
    routed = continue_mortal_wound_application(
        state=state,
        decisions=decisions,
        request_id=state.next_decision_request_id(),
        progress=progress,
        dice_manager=dice,
    )
    return _finish_mortal_wounds(state=state, decisions=decisions, routed=routed)


def apply_preparation_mortal_wound_decision(
    context: MortalWoundFeelNoPainContinuationContext,
) -> LifecycleStatus | None:
    routed = resolve_mortal_wound_decision(
        state=context.state,
        decisions=context.decisions,
        request=context.request,
        result=context.result,
        next_request_id=context.state.next_decision_request_id(),
        dice_manager=context.dice_manager,
    )
    return _finish_mortal_wounds(state=context.state, decisions=context.decisions, routed=routed)


def _finish_mortal_wounds(
    *, state: GameState, decisions: DecisionController, routed: MortalWoundRoutingResult
) -> LifecycleStatus | None:
    source = routed.progress.source_context
    if not isinstance(source, dict) or not isinstance(source.get("resolution_payload"), dict):
        raise GameLifecycleError("Unit grant preparation lacks mortal wound resolution context.")
    payload = source["resolution_payload"]
    assert isinstance(payload, dict)
    preparation = UnitGrantPreparation.from_payload(source[PREPARATION_KEY])
    if routed.request is not None:
        decisions.request_decision(routed.request)
        decisions.event_log.append(
            preparation.pending_event_type,
            {
                **payload,
                "request_id": routed.request.request_id,
                "remaining_mortal_wounds": routed.progress.remaining_mortal_wounds,
            },
        )
        return LifecycleStatus.waiting_for_decision(
            stage=state.stage,
            decision_request=routed.request,
            payload={
                **payload,
                "decision_type": routed.request.decision_type,
                "source_kind": preparation.mortal_wound_source_kind,
            },
        )
    if routed.application is None:
        raise GameLifecycleError("Unit grant preparation did not finish mortal wound allocation.")
    decisions.event_log.append(
        preparation.resolved_event_type,
        {
            **payload,
            "mortal_wound_application": validate_json_value(routed.application.to_payload()),
        },
    )
    return None


def is_preparation_mortal_wound_source(source_context: JsonValue) -> bool:
    return isinstance(source_context, dict) and PREPARATION_KEY in source_context


def mortal_wound_commitment_result_id(source_context: JsonValue) -> str:
    if not isinstance(source_context, dict):
        raise GameLifecycleError("Selected unit grant mortal wound context is malformed.")
    payload = source_context.get("resolution_payload")
    if not isinstance(payload, dict):
        raise GameLifecycleError("Selected unit grant mortal wound resolution context is missing.")
    return _string(payload, COMMITMENT_RESULT_KEY)


def _string(payload: dict[str, JsonValue], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise GameLifecycleError(f"Unit grant preparation lacks {key}.")
    return value
