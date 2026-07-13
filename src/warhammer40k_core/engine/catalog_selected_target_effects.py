from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.abilities import AbilityCatalogIndex, AbilityCatalogRecord
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.attack_sequence import AttackSequence
from warhammer40k_core.engine.attack_sequence_completion_hooks import (
    AttackSequenceCompletedContext,
    AttackSequenceCompletedHookBinding,
    successful_hit_target_unit_ids_for_sequence,
)
from warhammer40k_core.engine.battle_shock_hooks import BattleShockHookRegistry
from warhammer40k_core.engine.battle_shock_resolution import (
    apply_battle_shock_reroll_resolution_decision,
    is_battle_shock_reroll_request,
)
from warhammer40k_core.engine.catalog_rule_consumption import (
    CATALOG_IR_POST_SHOOT_HIT_TARGET_EFFECT_CONSUMER_ID,
    CATALOG_IR_SELECTED_TARGET_EFFECT_CONSUMER_ID,
    catalog_rule_current_placed_alive_model_instance_ids_for_unit,
)
from warhammer40k_core.engine.catalog_selected_target_battle_shock import (
    payload_optional_string as _payload_optional_string,
)
from warhammer40k_core.engine.catalog_selected_target_battle_shock import (
    resolve_selected_target_battle_shock_effect as _resolve_selected_target_battle_shock_effect,
)
from warhammer40k_core.engine.catalog_selected_target_effects_support import (
    SUPPORTED_SELECTED_EFFECT_KINDS as _SUPPORTED_SELECTED_EFFECT_KINDS,
)
from warhammer40k_core.engine.catalog_selected_target_effects_support import (
    active_player_id as _active_player_id,
)
from warhammer40k_core.engine.catalog_selected_target_effects_support import (
    army_for_player as _army_for_player,
)
from warhammer40k_core.engine.catalog_selected_target_effects_support import (
    battle_phase_kind as _battle_phase_kind,
)
from warhammer40k_core.engine.catalog_selected_target_effects_support import (
    catalog_selected_target_clauses_from_record as _catalog_selected_target_clauses_from_record,
)
from warhammer40k_core.engine.catalog_selected_target_effects_support import (
    clause_is_fight_start_selection as _clause_is_fight_start_selection,
)
from warhammer40k_core.engine.catalog_selected_target_effects_support import (
    clause_is_post_shoot_hit_target_selection as _clause_is_post_shoot_hit_target_selection,
)
from warhammer40k_core.engine.catalog_selected_target_effects_support import (
    effect_is_immediate_selected_target_battle_shock as _is_immediate_battle_shock,
)
from warhammer40k_core.engine.catalog_selected_target_effects_support import (
    effect_target_unit_ids as _effect_target_unit_ids,
)
from warhammer40k_core.engine.catalog_selected_target_effects_support import (
    effect_with_selected_target as _effect_with_selected_target,
)
from warhammer40k_core.engine.catalog_selected_target_effects_support import (
    eligible_selection_target_unit_ids as _eligible_selection_target_unit_ids,
)
from warhammer40k_core.engine.catalog_selected_target_effects_support import (
    has_fight_start_selected_target_records as _has_fight_start_selected_target_records,
)
from warhammer40k_core.engine.catalog_selected_target_effects_support import (
    has_post_shoot_hit_target_effect_runtime_records as _has_runtime_post_shoot_records,
)
from warhammer40k_core.engine.catalog_selected_target_effects_support import (
    payload_effect_records as _payload_effect_records,
)
from warhammer40k_core.engine.catalog_selected_target_effects_support import (
    payload_int as _payload_int,
)
from warhammer40k_core.engine.catalog_selected_target_effects_support import (
    payload_object as _payload_object,
)
from warhammer40k_core.engine.catalog_selected_target_effects_support import (
    payload_string as _payload_string,
)
from warhammer40k_core.engine.catalog_selected_target_effects_support import (
    payload_string_tuple as _payload_string_tuple,
)
from warhammer40k_core.engine.catalog_selected_target_effects_support import (
    post_shoot_selected_target_effect_attack_role as _post_shoot_effect_attack_role,
)
from warhammer40k_core.engine.catalog_selected_target_effects_support import (
    post_shoot_selected_target_effect_clauses_after as _post_shoot_effect_clauses_after,
)
from warhammer40k_core.engine.catalog_selected_target_effects_support import (
    record_has_supported_post_shoot_selected_target_effect as _record_has_supported_post_shoot,
)
from warhammer40k_core.engine.catalog_selected_target_effects_support import (
    runtime_clause_id_from_record as _runtime_clause_id_from_record,
)
from warhammer40k_core.engine.catalog_selected_target_effects_support import (
    selected_effect_clauses_after as _selected_effect_clauses_after,
)
from warhammer40k_core.engine.catalog_selected_target_effects_support import (
    selected_payload as _selected_payload,
)
from warhammer40k_core.engine.catalog_selected_target_effects_support import (
    selected_target_effect_expiration as _selected_target_effect_expiration,
)
from warhammer40k_core.engine.catalog_selected_target_effects_support import (
    selected_target_status_gate_allows as _selected_target_status_gate_allows,
)
from warhammer40k_core.engine.catalog_selected_target_effects_support import (
    selection_source_model_ids_for_record as _source_model_ids,
)
from warhammer40k_core.engine.catalog_selected_target_effects_support import (
    selection_weapon_names as _selection_weapon_names,
)
from warhammer40k_core.engine.catalog_selected_target_effects_support import (
    timing_window_id as _timing_window_id,
)
from warhammer40k_core.engine.catalog_selected_target_effects_support import (
    unit_scoped_generic_records_for_timing as _unit_scoped_generic_records_for_timing,
)
from warhammer40k_core.engine.catalog_selected_target_effects_support import (
    unit_statuses as _unit_statuses,
)
from warhammer40k_core.engine.catalog_selected_target_effects_support import (
    validate_ability_indexes as _validate_ability_indexes,
)
from warhammer40k_core.engine.catalog_selected_target_effects_support import (
    validate_armies as _validate_armies,
)
from warhammer40k_core.engine.catalog_selected_target_effects_support import (
    validate_effect_record_tuple as _validate_effect_record_tuple,
)
from warhammer40k_core.engine.catalog_selected_target_effects_support import (
    validate_unit as _validate_unit,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult, DecisionResultPayload
from warhammer40k_core.engine.effects import (
    GENERIC_RULE_EFFECT_KIND,
    EffectExpiration,
    EffectExpirationPayload,
    generic_rule_persisting_effect,
)
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.fight_phase_start_hooks import (
    SELECT_FACTION_RULE_FIGHT_PHASE_START_OPTION_DECISION_TYPE,
    FightPhaseStartHookBinding,
    FightPhaseStartRequestContext,
    FightPhaseStartResultContext,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
)
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.rules.rule_ir import RuleClause

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState

SELECT_CATALOG_POST_SHOOT_HIT_TARGET_EFFECT_DECISION_TYPE = (
    "select_catalog_post_shoot_hit_target_effect"
)
SELECT_CATALOG_POST_SHOOT_HIT_TARGET_EFFECT_SUBMISSION_KIND = (
    "select_catalog_post_shoot_hit_target_effect"
)
CATALOG_SELECTED_TARGET_EFFECT_SELECTED_EVENT = "catalog_selected_target_effect_selected"
CATALOG_POST_SHOOT_HIT_TARGET_EFFECT_SELECTED_EVENT = (
    "catalog_post_shoot_hit_target_effect_selected"
)
CATALOG_SELECTED_TARGET_BATTLE_SHOCK_SOURCE_KIND = "catalog_selected_target_effect"

_FIGHT_START_SUBMISSION_KIND = "catalog_selected_target_fight_start_effect"

_validate_identifier = IdentifierValidator(GameLifecycleError)


@dataclass(frozen=True, slots=True)
class _SelectedTargetOption:
    option_id: str
    target_unit_instance_id: str
    effect_records: tuple[dict[str, JsonValue], ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "option_id", _validate_identifier("option_id", self.option_id))
        object.__setattr__(
            self,
            "target_unit_instance_id",
            _validate_identifier("target_unit_instance_id", self.target_unit_instance_id),
        )
        object.__setattr__(
            self,
            "effect_records",
            _validate_effect_record_tuple(self.effect_records),
        )


@dataclass(frozen=True, slots=True)
class _SelectedTargetGroup:
    record: AbilityCatalogRecord
    player_id: str
    unit: UnitInstance
    source_model_instance_id: str | None
    selection_clause: RuleClause
    effect_clauses: tuple[RuleClause, ...]
    options: tuple[_SelectedTargetOption, ...]
    phase: BattlePhase
    hook_id: str
    submission_kind: str
    attack_sequence: AttackSequence | None = None
    attack_sequence_completed_event_id: str | None = None

    def __post_init__(self) -> None:
        if type(self.record) is not AbilityCatalogRecord:
            raise GameLifecycleError("Catalog selected-target group requires ability record.")
        object.__setattr__(self, "player_id", _validate_identifier("player_id", self.player_id))
        _validate_unit(self.unit)
        if self.source_model_instance_id is not None:
            object.__setattr__(
                self,
                "source_model_instance_id",
                _validate_identifier("source_model_instance_id", self.source_model_instance_id),
            )
        if type(self.selection_clause) is not RuleClause:
            raise GameLifecycleError("Catalog selected-target group requires selection clause.")
        if type(self.effect_clauses) is not tuple or not self.effect_clauses:
            raise GameLifecycleError("Catalog selected-target group requires effect clauses.")
        for clause in self.effect_clauses:
            if type(clause) is not RuleClause:
                raise GameLifecycleError("Catalog selected-target effect clauses are invalid.")
        if type(self.options) is not tuple or not self.options:
            raise GameLifecycleError("Catalog selected-target group requires options.")
        options = tuple(_validate_option(option) for option in self.options)
        if len({option.option_id for option in options}) != len(options):
            raise GameLifecycleError("Catalog selected-target options must not duplicate IDs.")
        object.__setattr__(self, "options", tuple(sorted(options, key=lambda item: item.option_id)))
        if type(self.phase) is not BattlePhase:
            raise GameLifecycleError("Catalog selected-target group requires BattlePhase.")
        object.__setattr__(self, "hook_id", _validate_identifier("hook_id", self.hook_id))
        object.__setattr__(
            self,
            "submission_kind",
            _validate_identifier("submission_kind", self.submission_kind),
        )
        if self.attack_sequence is not None and type(self.attack_sequence) is not AttackSequence:
            raise GameLifecycleError("Catalog selected-target group attack_sequence is invalid.")
        if self.attack_sequence_completed_event_id is not None:
            object.__setattr__(
                self,
                "attack_sequence_completed_event_id",
                _validate_identifier(
                    "attack_sequence_completed_event_id",
                    self.attack_sequence_completed_event_id,
                ),
            )

    @property
    def sort_key(self) -> tuple[str, str, str, str, str]:
        return (
            self.unit.unit_instance_id,
            self.record.record_id,
            self.selection_clause.clause_id,
            "" if self.source_model_instance_id is None else self.source_model_instance_id,
            ""
            if self.attack_sequence_completed_event_id is None
            else (self.attack_sequence_completed_event_id),
        )


@dataclass(frozen=True, slots=True)
class _SelectedTargetEffectRecording:
    effects: tuple[dict[str, JsonValue], ...]
    pending_status: LifecycleStatus | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "effects", _validate_effect_record_tuple(self.effects))
        if self.pending_status is not None and type(self.pending_status) is not LifecycleStatus:
            raise GameLifecycleError("Catalog selected-target pending status is invalid.")


@dataclass(frozen=True, slots=True)
class CatalogSelectedTargetEffectRuntime:
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex]
    armies: tuple[ArmyDefinition, ...]

    def __post_init__(self) -> None:
        indexes = _validate_ability_indexes(self.ability_indexes_by_player_id)
        armies = _validate_armies(self.armies)
        missing_ids = {army.player_id for army in armies} - set(indexes)
        if missing_ids:
            raise GameLifecycleError("Catalog selected-target runtime missing ability index.")
        object.__setattr__(self, "ability_indexes_by_player_id", MappingProxyType(dict(indexes)))
        object.__setattr__(self, "armies", armies)

    def fight_phase_start_bindings(self) -> tuple[FightPhaseStartHookBinding, ...]:
        if not _has_fight_start_selected_target_records(self.ability_indexes_by_player_id):
            return ()
        return (
            FightPhaseStartHookBinding(
                hook_id=CATALOG_IR_SELECTED_TARGET_EFFECT_CONSUMER_ID,
                source_id=CATALOG_IR_SELECTED_TARGET_EFFECT_CONSUMER_ID,
                request_handler=self.fight_phase_start_request,
                result_handler=self.apply_fight_phase_start_result,
            ),
        )

    def attack_sequence_completed_bindings(
        self,
    ) -> tuple[AttackSequenceCompletedHookBinding, ...]:
        if not _has_runtime_post_shoot_records(self.ability_indexes_by_player_id, self.armies):
            return ()
        return (
            AttackSequenceCompletedHookBinding(
                hook_id=CATALOG_IR_POST_SHOOT_HIT_TARGET_EFFECT_CONSUMER_ID,
                source_id=CATALOG_IR_POST_SHOOT_HIT_TARGET_EFFECT_CONSUMER_ID,
                handler=self.post_shoot_hit_target_request,
            ),
        )

    def fight_phase_start_request(
        self,
        context: FightPhaseStartRequestContext,
    ) -> DecisionRequest | None:
        groups = _fight_start_selected_target_groups(
            ability_indexes_by_player_id=self.ability_indexes_by_player_id,
            armies=self.armies,
            context=context,
        )
        if not groups:
            return None
        return _selected_target_request(
            state=context.state,
            group=groups[0],
            decision_type=SELECT_FACTION_RULE_FIGHT_PHASE_START_OPTION_DECISION_TYPE,
        )

    def apply_fight_phase_start_result(
        self,
        context: FightPhaseStartResultContext,
    ) -> bool | LifecycleStatus:
        if type(context) is not FightPhaseStartResultContext:
            raise GameLifecycleError("Catalog selected-target Fight-start requires context.")
        request_payload = _payload_object(context.request.payload)
        if request_payload.get("hook_id") != CATALOG_IR_SELECTED_TARGET_EFFECT_CONSUMER_ID:
            return False
        invalid_status = _invalid_selected_target_effect_status(
            state=context.state,
            request=context.request,
            result=context.result,
            expected_decision_type=SELECT_FACTION_RULE_FIGHT_PHASE_START_OPTION_DECISION_TYPE,
            expected_submission_kind=_FIGHT_START_SUBMISSION_KIND,
            expected_phase=BattlePhase.FIGHT,
            invalid_reason="invalid_catalog_selected_target_fight_start_result",
        )
        if invalid_status is not None:
            return invalid_status
        payload = _payload_object(context.result.payload)
        recording = _record_selected_target_effects_from_payload(
            state=context.state,
            decisions=context.decisions,
            result=context.result,
            payload=payload,
            phase=BattlePhase.FIGHT,
            event_type=CATALOG_SELECTED_TARGET_EFFECT_SELECTED_EVENT,
        )
        if recording.pending_status is not None:
            return recording.pending_status
        _append_selected_target_event(
            state=context.state,
            decisions=context.decisions,
            result=context.result,
            payload=payload,
            effects=recording.effects,
            event_type=CATALOG_SELECTED_TARGET_EFFECT_SELECTED_EVENT,
            phase=BattlePhase.FIGHT,
        )
        return True

    def post_shoot_hit_target_request(
        self,
        context: AttackSequenceCompletedContext,
    ) -> LifecycleStatus | None:
        if type(context) is not AttackSequenceCompletedContext:
            raise GameLifecycleError("Catalog post-shoot target effect requires context.")
        groups = _post_shoot_hit_target_effect_groups(
            ability_indexes_by_player_id=self.ability_indexes_by_player_id,
            armies=self.armies,
            context=context,
        )
        if not groups:
            return None
        resolved = _resolved_post_shoot_target_effect_group_keys(context.decisions)
        unresolved = tuple(
            group for group in groups if _post_shoot_group_key(group) not in resolved
        )
        if not unresolved:
            return None
        group = unresolved[0]
        request = _selected_target_request(
            state=context.state,
            group=group,
            decision_type=SELECT_CATALOG_POST_SHOOT_HIT_TARGET_EFFECT_DECISION_TYPE,
        )
        context.decisions.request_decision(request)
        context.decisions.event_log.append(
            "catalog_post_shoot_hit_target_effect_requested",
            validate_json_value(
                {
                    "game_id": context.state.game_id,
                    "battle_round": context.state.battle_round,
                    "phase": BattlePhase.SHOOTING.value,
                    "active_player_id": context.state.active_player_id,
                    "player_id": group.player_id,
                    "hook_id": CATALOG_IR_POST_SHOOT_HIT_TARGET_EFFECT_CONSUMER_ID,
                    "request_id": request.request_id,
                    "catalog_record_id": group.record.record_id,
                    "source_rule_id": group.record.definition.source_id,
                    "unit_instance_id": group.unit.unit_instance_id,
                    "source_model_instance_id": group.source_model_instance_id,
                    "selection_clause_id": group.selection_clause.clause_id,
                    "attack_sequence_id": (
                        None if group.attack_sequence is None else group.attack_sequence.sequence_id
                    ),
                    "attack_sequence_completed_event_id": (
                        group.attack_sequence_completed_event_id
                    ),
                    "available_target_unit_instance_ids": [
                        option.target_unit_instance_id for option in group.options
                    ],
                    "phase_body_status": "catalog_post_shoot_hit_target_effect_pending",
                }
            ),
        )
        return LifecycleStatus.waiting_for_decision(
            stage=GameLifecycleStage.BATTLE,
            decision_request=request,
            payload=validate_json_value(
                {
                    "phase": BattlePhase.SHOOTING.value,
                    "battle_round": context.state.battle_round,
                    "active_player_id": context.state.active_player_id,
                    "player_id": group.player_id,
                    "pending_request_id": request.request_id,
                    "phase_body_status": "catalog_post_shoot_hit_target_effect_pending",
                }
            ),
        )


def catalog_selected_target_fight_phase_start_hook_bindings(
    *,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    armies: tuple[ArmyDefinition, ...],
) -> tuple[FightPhaseStartHookBinding, ...]:
    return CatalogSelectedTargetEffectRuntime(
        ability_indexes_by_player_id=ability_indexes_by_player_id,
        armies=armies,
    ).fight_phase_start_bindings()


def catalog_selected_target_attack_sequence_completed_hook_bindings(
    *,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    armies: tuple[ArmyDefinition, ...],
) -> tuple[AttackSequenceCompletedHookBinding, ...]:
    return CatalogSelectedTargetEffectRuntime(
        ability_indexes_by_player_id=ability_indexes_by_player_id,
        armies=armies,
    ).attack_sequence_completed_bindings()


def invalid_catalog_post_shoot_hit_target_effect_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
) -> LifecycleStatus | None:
    return _invalid_selected_target_effect_status(
        state=state,
        request=request,
        result=result,
        expected_decision_type=SELECT_CATALOG_POST_SHOOT_HIT_TARGET_EFFECT_DECISION_TYPE,
        expected_submission_kind=SELECT_CATALOG_POST_SHOOT_HIT_TARGET_EFFECT_SUBMISSION_KIND,
        expected_phase=BattlePhase.SHOOTING,
        invalid_reason="invalid_catalog_post_shoot_hit_target_effect_result",
    )


def apply_catalog_post_shoot_hit_target_effect_result(
    *,
    state: GameState,
    decisions: DecisionController,
    result: DecisionResult,
    battle_shock_hooks: BattleShockHookRegistry,
    runtime_modifier_registry: RuntimeModifierRegistry,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
) -> LifecycleStatus | None:
    if type(decisions) is not DecisionController:
        raise GameLifecycleError("Catalog post-shoot target effect apply requires decisions.")
    if type(result) is not DecisionResult:
        raise GameLifecycleError("Catalog post-shoot target effect apply requires result.")
    if type(battle_shock_hooks) is not BattleShockHookRegistry:
        raise GameLifecycleError("Catalog post-shoot target effect requires Battle-shock hooks.")
    if type(runtime_modifier_registry) is not RuntimeModifierRegistry:
        raise GameLifecycleError("Catalog post-shoot target effect requires runtime modifiers.")
    record = decisions.record_for_result(result)
    invalid_status = invalid_catalog_post_shoot_hit_target_effect_status(
        state=state,
        request=record.request,
        result=record.result,
    )
    if invalid_status is not None:
        return invalid_status
    payload = _payload_object(record.result.payload)
    recording = _record_selected_target_effects_from_payload(
        state=state,
        decisions=decisions,
        result=record.result,
        payload=payload,
        phase=BattlePhase.SHOOTING,
        event_type=CATALOG_POST_SHOOT_HIT_TARGET_EFFECT_SELECTED_EVENT,
        battle_shock_hooks=battle_shock_hooks,
        runtime_modifier_registry=runtime_modifier_registry,
        ability_indexes_by_player_id=ability_indexes_by_player_id,
    )
    if recording.pending_status is not None:
        return recording.pending_status
    _append_selected_target_event(
        state=state,
        decisions=decisions,
        result=record.result,
        payload=payload,
        effects=recording.effects,
        event_type=CATALOG_POST_SHOOT_HIT_TARGET_EFFECT_SELECTED_EVENT,
        phase=BattlePhase.SHOOTING,
    )
    return None


def is_catalog_selected_target_battle_shock_reroll_request(request: DecisionRequest) -> bool:
    return is_battle_shock_reroll_request(
        request,
        source_kind=CATALOG_SELECTED_TARGET_BATTLE_SHOCK_SOURCE_KIND,
    )


def apply_catalog_selected_target_battle_shock_reroll_decision(
    *,
    state: GameState,
    decisions: DecisionController,
    result: DecisionResult,
    battle_shock_hooks: BattleShockHookRegistry,
    runtime_modifier_registry: RuntimeModifierRegistry,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
) -> LifecycleStatus | None:
    resolved_payload = apply_battle_shock_reroll_resolution_decision(
        state=state,
        decisions=decisions,
        result=result,
        battle_shock_hooks=battle_shock_hooks,
        expected_source_kind=CATALOG_SELECTED_TARGET_BATTLE_SHOCK_SOURCE_KIND,
    )
    original_result = DecisionResult.from_payload(
        cast(
            DecisionResultPayload,
            _payload_object(resolved_payload.get("selected_target_decision_result")),
        )
    )
    selected_payload = _payload_object(resolved_payload.get("selected_target_payload"))
    recorded_effects = list(
        _payload_json_object_tuple(
            resolved_payload,
            key="selected_target_recorded_effects_before_battle_shock",
        )
    )
    recorded_effects.append(resolved_payload)
    remaining_records = _payload_json_object_tuple(
        resolved_payload,
        key="selected_target_remaining_effect_records_after_battle_shock",
    )
    if remaining_records:
        recording = _record_selected_target_effect_records(
            state=state,
            decisions=decisions,
            result=original_result,
            payload=selected_payload,
            effect_records=remaining_records,
            phase=BattlePhase.SHOOTING,
            event_type=CATALOG_POST_SHOOT_HIT_TARGET_EFFECT_SELECTED_EVENT,
            battle_shock_hooks=battle_shock_hooks,
            runtime_modifier_registry=runtime_modifier_registry,
            ability_indexes_by_player_id=ability_indexes_by_player_id,
            initial_recorded=tuple(recorded_effects),
            effect_index_offset=_payload_int(
                resolved_payload,
                key="selected_target_remaining_effect_start_index",
            ),
        )
        if recording.pending_status is not None:
            return recording.pending_status
        effects = recording.effects
    else:
        effects = tuple(recorded_effects)
    _append_selected_target_event(
        state=state,
        decisions=decisions,
        result=original_result,
        payload=selected_payload,
        effects=effects,
        event_type=CATALOG_POST_SHOOT_HIT_TARGET_EFFECT_SELECTED_EVENT,
        phase=BattlePhase.SHOOTING,
    )
    return None


def _fight_start_selected_target_groups(
    *,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    armies: tuple[ArmyDefinition, ...],
    context: FightPhaseStartRequestContext,
) -> tuple[_SelectedTargetGroup, ...]:
    if context.state.current_battle_phase is not BattlePhase.FIGHT:
        return ()
    if context.state.battlefield_state is None:
        return ()
    groups: list[_SelectedTargetGroup] = []
    for army in sorted(armies, key=lambda item: item.player_id):
        index = ability_indexes_by_player_id.get(army.player_id)
        if index is None:
            raise GameLifecycleError("Catalog selected-target missing ability index.")
        for unit in sorted(army.units, key=lambda item: item.unit_instance_id):
            current_model_ids = catalog_rule_current_placed_alive_model_instance_ids_for_unit(
                state=context.state,
                unit=unit,
            )
            if not current_model_ids:
                continue
            for record in _unit_scoped_generic_records_for_timing(
                ability_index=index,
                unit=unit,
                current_model_instance_ids=current_model_ids,
                trigger_kind=TimingTriggerKind.START_PHASE,
            ):
                groups.extend(
                    _fight_start_groups_for_record(
                        state=context.state,
                        army=army,
                        unit=unit,
                        current_model_instance_ids=current_model_ids,
                        record=record,
                    )
                )
    return tuple(sorted(groups, key=lambda group: group.sort_key))


def _post_shoot_hit_target_effect_groups(
    *,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    armies: tuple[ArmyDefinition, ...],
    context: AttackSequenceCompletedContext,
) -> tuple[_SelectedTargetGroup, ...]:
    if (
        context.source_phase is not BattlePhase.SHOOTING
        or context.attack_sequence.source_phase is not BattlePhase.SHOOTING
        or context.attack_sequence.attacker_player_id != context.state.active_player_id
    ):
        return ()
    player_id = _validate_identifier("player_id", context.attack_sequence.attacker_player_id)
    army = _army_for_player(armies, player_id=player_id)
    rules_unit = rules_unit_view_by_id(
        state=context.state,
        unit_instance_id=context.attack_sequence.attacking_unit_instance_id,
    )
    index = ability_indexes_by_player_id.get(player_id)
    if index is None:
        raise GameLifecycleError("Catalog post-shoot target effect missing ability index.")
    groups: list[_SelectedTargetGroup] = []
    for component in sorted(
        rules_unit.components,
        key=lambda value: value.unit.unit_instance_id,
    ):
        unit = component.unit
        current_model_ids = catalog_rule_current_placed_alive_model_instance_ids_for_unit(
            state=context.state,
            unit=unit,
        )
        if not current_model_ids:
            continue
        for record in _unit_scoped_generic_records_for_timing(
            ability_index=index,
            unit=unit,
            current_model_instance_ids=current_model_ids,
            trigger_kind=TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_HAS_SHOT,
        ):
            if not _record_has_supported_post_shoot(record):
                continue
            groups.extend(
                _post_shoot_groups_for_record(
                    state=context.state,
                    decisions=context.decisions,
                    army=army,
                    unit=unit,
                    current_model_instance_ids=current_model_ids,
                    record=record,
                    attack_sequence=context.attack_sequence,
                    attack_sequence_completed_event_id=(context.attack_sequence_completed_event_id),
                )
            )
    return tuple(sorted(groups, key=lambda group: group.sort_key))


def _fight_start_groups_for_record(
    *,
    state: GameState,
    army: ArmyDefinition,
    unit: UnitInstance,
    current_model_instance_ids: tuple[str, ...],
    record: AbilityCatalogRecord,
) -> tuple[_SelectedTargetGroup, ...]:
    clauses = _catalog_selected_target_clauses_from_record(record)
    runtime_clause_id = _runtime_clause_id_from_record(record)
    groups: list[_SelectedTargetGroup] = []
    for index, selection_clause in enumerate(clauses):
        if runtime_clause_id is not None and runtime_clause_id != selection_clause.clause_id:
            continue
        if not _clause_is_fight_start_selection(selection_clause):
            continue
        effect_clauses = _selected_effect_clauses_after(clauses, index)
        if not effect_clauses:
            continue
        for source_model_id in _source_model_ids(
            record, unit, selection_clause, current_model_instance_ids
        ):
            target_ids = _eligible_selection_target_unit_ids(
                state=state,
                source_player_id=army.player_id,
                source_unit_instance_id=unit.unit_instance_id,
                source_model_instance_id=source_model_id,
                selection_clause=selection_clause,
                explicit_target_unit_ids=None,
            )
            options = _options_for_targets(
                state=state,
                record=record,
                player_id=army.player_id,
                unit=unit,
                source_model_instance_id=source_model_id,
                selection_clause=selection_clause,
                effect_clauses=effect_clauses,
                selected_target_unit_ids=target_ids,
                phase=BattlePhase.FIGHT,
                hook_id=CATALOG_IR_SELECTED_TARGET_EFFECT_CONSUMER_ID,
                submission_kind=_FIGHT_START_SUBMISSION_KIND,
                attack_sequence=None,
                attack_sequence_completed_event_id=None,
            )
            if options:
                groups.append(
                    _SelectedTargetGroup(
                        record=record,
                        player_id=army.player_id,
                        unit=unit,
                        source_model_instance_id=source_model_id,
                        selection_clause=selection_clause,
                        effect_clauses=effect_clauses,
                        options=options,
                        phase=BattlePhase.FIGHT,
                        hook_id=CATALOG_IR_SELECTED_TARGET_EFFECT_CONSUMER_ID,
                        submission_kind=_FIGHT_START_SUBMISSION_KIND,
                    )
                )
    return tuple(groups)


def _post_shoot_groups_for_record(
    *,
    state: GameState,
    decisions: DecisionController,
    army: ArmyDefinition,
    unit: UnitInstance,
    current_model_instance_ids: tuple[str, ...],
    record: AbilityCatalogRecord,
    attack_sequence: AttackSequence,
    attack_sequence_completed_event_id: str,
) -> tuple[_SelectedTargetGroup, ...]:
    clauses = _catalog_selected_target_clauses_from_record(record)
    runtime_clause_id = _runtime_clause_id_from_record(record)
    groups: list[_SelectedTargetGroup] = []
    for index, selection_clause in enumerate(clauses):
        if runtime_clause_id is not None and runtime_clause_id != selection_clause.clause_id:
            continue
        if not _clause_is_post_shoot_hit_target_selection(selection_clause):
            continue
        effect_clauses = _post_shoot_effect_clauses_after(clauses, index)
        if not effect_clauses:
            continue
        for source_model_id in _source_model_ids(
            record, unit, selection_clause, current_model_instance_ids
        ):
            hit_target_ids = successful_hit_target_unit_ids_for_sequence(
                decisions=decisions,
                sequence=attack_sequence,
                attacker_model_instance_id=source_model_id,
                weapon_names=_selection_weapon_names(selection_clause),
            )
            if not hit_target_ids:
                continue
            target_ids = _eligible_selection_target_unit_ids(
                state=state,
                source_player_id=army.player_id,
                source_unit_instance_id=unit.unit_instance_id,
                source_model_instance_id=source_model_id,
                selection_clause=selection_clause,
                explicit_target_unit_ids=hit_target_ids,
            )
            options = _options_for_targets(
                state=state,
                record=record,
                player_id=army.player_id,
                unit=unit,
                source_model_instance_id=source_model_id,
                selection_clause=selection_clause,
                effect_clauses=effect_clauses,
                selected_target_unit_ids=target_ids,
                phase=BattlePhase.SHOOTING,
                hook_id=CATALOG_IR_POST_SHOOT_HIT_TARGET_EFFECT_CONSUMER_ID,
                submission_kind=SELECT_CATALOG_POST_SHOOT_HIT_TARGET_EFFECT_SUBMISSION_KIND,
                attack_sequence=attack_sequence,
                attack_sequence_completed_event_id=attack_sequence_completed_event_id,
            )
            if options:
                groups.append(
                    _SelectedTargetGroup(
                        record=record,
                        player_id=army.player_id,
                        unit=unit,
                        source_model_instance_id=source_model_id,
                        selection_clause=selection_clause,
                        effect_clauses=effect_clauses,
                        options=options,
                        phase=BattlePhase.SHOOTING,
                        hook_id=CATALOG_IR_POST_SHOOT_HIT_TARGET_EFFECT_CONSUMER_ID,
                        submission_kind=(
                            SELECT_CATALOG_POST_SHOOT_HIT_TARGET_EFFECT_SUBMISSION_KIND
                        ),
                        attack_sequence=attack_sequence,
                        attack_sequence_completed_event_id=(attack_sequence_completed_event_id),
                    )
                )
    return tuple(groups)


def _options_for_targets(
    *,
    state: GameState,
    record: AbilityCatalogRecord,
    player_id: str,
    unit: UnitInstance,
    source_model_instance_id: str | None,
    selection_clause: RuleClause,
    effect_clauses: tuple[RuleClause, ...],
    selected_target_unit_ids: tuple[str, ...],
    phase: BattlePhase,
    hook_id: str,
    submission_kind: str,
    attack_sequence: AttackSequence | None,
    attack_sequence_completed_event_id: str | None,
) -> tuple[_SelectedTargetOption, ...]:
    options: list[_SelectedTargetOption] = []
    for target_unit_id in selected_target_unit_ids:
        effect_records = _effect_records_for_selected_target(
            state=state,
            record=record,
            player_id=player_id,
            unit=unit,
            source_model_instance_id=source_model_instance_id,
            selection_clause=selection_clause,
            effect_clauses=effect_clauses,
            selected_target_unit_instance_id=target_unit_id,
            phase=phase,
            hook_id=hook_id,
            submission_kind=submission_kind,
            attack_sequence=attack_sequence,
            attack_sequence_completed_event_id=attack_sequence_completed_event_id,
        )
        if not effect_records:
            continue
        options.append(
            _SelectedTargetOption(
                option_id=_selected_target_option_id(
                    record=record,
                    unit=unit,
                    source_model_instance_id=source_model_instance_id,
                    selection_clause=selection_clause,
                    target_unit_instance_id=target_unit_id,
                    attack_sequence_completed_event_id=attack_sequence_completed_event_id,
                ),
                target_unit_instance_id=target_unit_id,
                effect_records=effect_records,
            )
        )
    return tuple(options)


def _effect_records_for_selected_target(
    *,
    state: GameState,
    record: AbilityCatalogRecord,
    player_id: str,
    unit: UnitInstance,
    source_model_instance_id: str | None,
    selection_clause: RuleClause,
    effect_clauses: tuple[RuleClause, ...],
    selected_target_unit_instance_id: str,
    phase: BattlePhase,
    hook_id: str,
    submission_kind: str,
    attack_sequence: AttackSequence | None,
    attack_sequence_completed_event_id: str | None,
) -> tuple[dict[str, JsonValue], ...]:
    from warhammer40k_core.engine.rule_execution import (
        RuleExecutionContext,
        rule_ir_from_execution_payload,
    )

    selected_target_id = _validate_identifier(
        "selected_target_unit_instance_id",
        selected_target_unit_instance_id,
    )
    rule_ir = rule_ir_from_execution_payload(record.definition.replay_payload)
    records: list[dict[str, JsonValue]] = []
    for clause in effect_clauses:
        if not _selected_target_status_gate_allows(
            state=state,
            clause=clause,
            selected_target_unit_instance_id=selected_target_id,
        ):
            continue
        target_unit_ids = _effect_target_unit_ids(
            state=state,
            source_player_id=player_id,
            source_unit=unit,
            selected_target_unit_instance_id=selected_target_id,
            clause=clause,
        )
        if not target_unit_ids:
            continue
        for effect_index, effect in enumerate(clause.effects):
            if effect.kind not in _SUPPORTED_SELECTED_EFFECT_KINDS:
                raise GameLifecycleError("Catalog selected-target effect kind is unsupported.")
            immediate_effect_kind = (
                "force_battle_shock_test"
                if (clause.duration is None and _is_immediate_battle_shock(effect))
                else None
            )
            transformed_effect = _effect_with_selected_target(
                effect,
                selected_target_unit_instance_id=selected_target_id,
                normalized_attack_role=(
                    _post_shoot_effect_attack_role(clause=clause, effect=effect)
                    if hook_id == CATALOG_IR_POST_SHOOT_HIT_TARGET_EFFECT_CONSUMER_ID
                    and immediate_effect_kind is None
                    else None
                ),
            )
            context = RuleExecutionContext(
                game_id=state.game_id,
                player_id=player_id,
                battle_round=state.battle_round,
                phase=_battle_phase_kind(phase),
                active_player_id=state.active_player_id,
                timing_window_id=_timing_window_id(phase),
                source_unit_instance_id=unit.unit_instance_id,
                source_model_instance_id=source_model_instance_id,
                target_unit_instance_ids=target_unit_ids,
                source_keywords=tuple(sorted((*unit.keywords, *unit.faction_keywords))),
                trigger_payload=validate_json_value(
                    {
                        "selected_target_unit_instance_ids": [selected_target_id],
                        "selected_target_unit_instance_id": selected_target_id,
                        "target_unit_statuses": _unit_statuses(state, selected_target_id),
                        "catalog_record_id": record.record_id,
                        "selection_clause_id": selection_clause.clause_id,
                        "submission_kind": submission_kind,
                    }
                ),
                state=state,
                event_log=None,
                record_persisting_effects=False,
            )
            effect_record: dict[str, object] = {
                "source_rule_id": record.definition.source_id,
                "owner_player_id": player_id,
                "target_unit_instance_ids": list(target_unit_ids),
                "started_battle_round": state.battle_round,
                "started_phase": _battle_phase_kind(phase).value,
                "expiration": _selected_target_effect_expiration(
                    state=state,
                    phase=phase,
                    clause=clause,
                ).to_payload(),
                "effect_payload": {
                    "effect_kind": GENERIC_RULE_EFFECT_KIND,
                    "rule_id": rule_ir.rule_id,
                    "source_id": record.definition.source_id,
                    "rule_ir_hash": rule_ir.ir_hash(),
                    "clause_id": clause.clause_id,
                    "source_span": clause.source_span.to_payload(),
                    "target": None if clause.target is None else clause.target.to_payload(),
                    "target_unit_instance_ids": list(target_unit_ids),
                    "duration": None if clause.duration is None else clause.duration.to_payload(),
                    "effect": transformed_effect.to_payload(),
                    "conditions": [condition.to_payload() for condition in clause.conditions],
                    "context": context.to_payload(),
                    "catalog_selected_target": {
                        "hook_id": hook_id,
                        "submission_kind": submission_kind,
                        "catalog_record_id": record.record_id,
                        "ability_id": record.definition.ability_id,
                        "ability_name": record.definition.name,
                        "source_unit_instance_id": unit.unit_instance_id,
                        "source_model_instance_id": source_model_instance_id,
                        "selection_clause_id": selection_clause.clause_id,
                        "selected_target_unit_instance_id": selected_target_id,
                        "attack_sequence_id": (
                            None if attack_sequence is None else attack_sequence.sequence_id
                        ),
                        "attack_sequence_completed_event_id": attack_sequence_completed_event_id,
                    },
                },
                "catalog_record_id": record.record_id,
                "ability_id": record.definition.ability_id,
                "ability_name": record.definition.name,
                "source_unit_instance_id": unit.unit_instance_id,
                "source_model_instance_id": source_model_instance_id,
                "selection_clause_id": selection_clause.clause_id,
                "effect_clause_id": clause.clause_id,
                "effect_index": effect_index,
                "selected_target_unit_instance_id": selected_target_id,
            }
            if immediate_effect_kind is not None:
                effect_record["immediate_effect_kind"] = immediate_effect_kind
            records.append(cast(dict[str, JsonValue], validate_json_value(effect_record)))
    return tuple(records)


def _selected_target_request(
    *,
    state: GameState,
    group: _SelectedTargetGroup,
    decision_type: str,
) -> DecisionRequest:
    common_payload = _selected_target_base_payload(state=state, group=group)
    return DecisionRequest(
        request_id=state.next_decision_request_id(),
        decision_type=decision_type,
        actor_id=group.player_id,
        payload=validate_json_value(
            {
                **common_payload,
                "available_target_unit_instance_ids": [
                    option.target_unit_instance_id for option in group.options
                ],
                "available_catalog_selected_target_options": [
                    _selected_target_option_selection_payload(option) for option in group.options
                ],
            }
        ),
        options=tuple(
            DecisionOption(
                option_id=option.option_id,
                label=f"Select {option.target_unit_instance_id}",
                payload=validate_json_value(
                    {
                        **common_payload,
                        "selected_catalog_target_effect": (
                            _selected_target_option_selection_payload(option)
                        ),
                        "generic_rule_effect_records": list(option.effect_records),
                    }
                ),
            )
            for option in group.options
        ),
    )


def _selected_target_base_payload(
    *,
    state: GameState,
    group: _SelectedTargetGroup,
) -> dict[str, JsonValue]:
    from warhammer40k_core.engine.rule_execution import rule_ir_from_execution_payload

    rule_ir = rule_ir_from_execution_payload(group.record.definition.replay_payload)
    payload: dict[str, JsonValue] = {
        "submission_kind": group.submission_kind,
        "hook_id": group.hook_id,
        "game_id": state.game_id,
        "battle_round": state.battle_round,
        "phase": group.phase.value,
        "active_player_id": _active_player_id(state),
        "player_id": group.player_id,
        "catalog_record_id": group.record.record_id,
        "ability_id": group.record.definition.ability_id,
        "ability_name": group.record.definition.name,
        "source_rule_id": group.record.definition.source_id,
        "rule_ir_hash": rule_ir.ir_hash(),
        "source_unit_instance_id": group.unit.unit_instance_id,
        "source_model_instance_id": group.source_model_instance_id,
        "selection_clause_id": group.selection_clause.clause_id,
        "effect_clause_ids": [clause.clause_id for clause in group.effect_clauses],
    }
    if group.attack_sequence is not None:
        payload["attack_sequence_id"] = group.attack_sequence.sequence_id
        payload["attack_sequence"] = validate_json_value(group.attack_sequence.to_payload())
    if group.attack_sequence_completed_event_id is not None:
        payload["attack_sequence_completed_event_id"] = group.attack_sequence_completed_event_id
    return payload


def _record_selected_target_effects_from_payload(
    *,
    state: GameState,
    decisions: DecisionController,
    result: DecisionResult,
    payload: Mapping[str, object],
    phase: BattlePhase,
    event_type: str,
    battle_shock_hooks: BattleShockHookRegistry | None = None,
    runtime_modifier_registry: RuntimeModifierRegistry | None = None,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex] = MappingProxyType({}),
) -> _SelectedTargetEffectRecording:
    if type(decisions) is not DecisionController:
        raise GameLifecycleError("Catalog selected-target effect recording requires decisions.")
    return _record_selected_target_effect_records(
        state=state,
        decisions=decisions,
        result=result,
        payload=payload,
        effect_records=tuple(
            cast(dict[str, JsonValue], validate_json_value(effect_record))
            for effect_record in _payload_effect_records(payload)
        ),
        phase=phase,
        event_type=event_type,
        battle_shock_hooks=battle_shock_hooks,
        runtime_modifier_registry=runtime_modifier_registry,
        ability_indexes_by_player_id=ability_indexes_by_player_id,
        initial_recorded=(),
        effect_index_offset=0,
    )


def _record_selected_target_effect_records(
    *,
    state: GameState,
    decisions: DecisionController,
    result: DecisionResult,
    payload: Mapping[str, object],
    effect_records: tuple[dict[str, JsonValue], ...],
    phase: BattlePhase,
    event_type: str,
    battle_shock_hooks: BattleShockHookRegistry | None,
    runtime_modifier_registry: RuntimeModifierRegistry | None,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    initial_recorded: tuple[dict[str, JsonValue], ...],
    effect_index_offset: int,
) -> _SelectedTargetEffectRecording:
    if type(decisions) is not DecisionController:
        raise GameLifecycleError("Catalog selected-target effect recording requires decisions.")
    recorded: list[dict[str, JsonValue]] = list(_validate_effect_record_tuple(initial_recorded))
    for index, record in enumerate(effect_records):
        target_unit_ids = _payload_string_tuple(record, key="target_unit_instance_ids")
        effect_payload = _payload_object(record["effect_payload"])
        immediate_effect_kind = _payload_optional_string(record, key="immediate_effect_kind")
        if immediate_effect_kind == "force_battle_shock_test":
            if battle_shock_hooks is None or runtime_modifier_registry is None:
                raise GameLifecycleError(
                    "Catalog selected-target Battle-shock requires runtime hooks."
                )
            resolution = _resolve_selected_target_battle_shock_effect(
                state=state,
                decisions=decisions,
                result=result,
                payload=payload,
                record=record,
                effect_payload=effect_payload,
                battle_shock_hooks=battle_shock_hooks,
                runtime_modifier_registry=runtime_modifier_registry,
                ability_indexes_by_player_id=ability_indexes_by_player_id,
                target_unit_ids=target_unit_ids,
                recorded_effects_before_battle_shock=tuple(recorded),
                remaining_effect_records_after_battle_shock=tuple(effect_records[index + 1 :]),
                remaining_effect_start_index=effect_index_offset + index + 1,
            )
            if resolution.pending_status is not None:
                return _SelectedTargetEffectRecording(
                    effects=tuple(recorded),
                    pending_status=resolution.pending_status,
                )
            if resolution.resolved_payload is None:
                raise GameLifecycleError("Catalog selected-target Battle-shock did not resolve.")
            recorded.append(resolution.resolved_payload)
            continue
        persisting_effect = generic_rule_persisting_effect(
            effect_id=f"{result.result_id}:{event_type}:{effect_index_offset + index:03d}",
            source_rule_id=_payload_string(record, key="source_rule_id"),
            owner_player_id=_payload_string(record, key="owner_player_id"),
            target_unit_instance_ids=target_unit_ids,
            started_battle_round=_payload_int(record, key="started_battle_round"),
            started_phase=BattlePhaseKind(_payload_string(record, key="started_phase")),
            expiration=EffectExpiration.from_payload(
                cast(EffectExpirationPayload, record["expiration"])
            ),
            effect_payload=validate_json_value(effect_payload),
        )
        if phase.value != _payload_string(payload, key="phase"):
            raise GameLifecycleError("Catalog selected-target phase drift.")
        state.record_persisting_effect(persisting_effect)
        recorded.append(
            cast(
                dict[str, JsonValue],
                validate_json_value(persisting_effect.to_payload()),
            )
        )
    return _SelectedTargetEffectRecording(effects=tuple(recorded), pending_status=None)


def _append_selected_target_event(
    *,
    state: GameState,
    decisions: DecisionController,
    result: DecisionResult,
    payload: Mapping[str, object],
    effects: tuple[dict[str, JsonValue], ...],
    event_type: str,
    phase: BattlePhase,
) -> None:
    selected_payload = _selected_payload(payload)
    decisions.event_log.append(
        event_type,
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": phase.value,
                "active_player_id": state.active_player_id,
                "player_id": result.actor_id,
                "request_id": result.request_id,
                "result_id": result.result_id,
                "selected_option_id": result.selected_option_id,
                "hook_id": _payload_string(payload, key="hook_id"),
                "catalog_record_id": _payload_string(payload, key="catalog_record_id"),
                "source_rule_id": _payload_string(payload, key="source_rule_id"),
                "source_unit_instance_id": _payload_string(
                    payload,
                    key="source_unit_instance_id",
                ),
                "source_model_instance_id": payload.get("source_model_instance_id"),
                "selection_clause_id": _payload_string(payload, key="selection_clause_id"),
                "target_unit_instance_id": _payload_string(
                    selected_payload,
                    key="target_unit_instance_id",
                ),
                "attack_sequence_id": payload.get("attack_sequence_id"),
                "attack_sequence_completed_event_id": (
                    payload.get("attack_sequence_completed_event_id")
                ),
                "persisting_effects": list(effects),
            }
        ),
    )


def _payload_json_object_tuple(
    payload: Mapping[str, JsonValue],
    *,
    key: str,
) -> tuple[dict[str, JsonValue], ...]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise GameLifecycleError(f"Catalog selected-target payload {key} must be a list.")
    records: list[dict[str, JsonValue]] = []
    for item in value:
        if not isinstance(item, dict):
            raise GameLifecycleError(f"Catalog selected-target payload {key} must be objects.")
        records.append(cast(dict[str, JsonValue], validate_json_value(item)))
    return tuple(records)


def _invalid_selected_target_effect_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
    expected_decision_type: str,
    expected_submission_kind: str,
    expected_phase: BattlePhase,
    invalid_reason: str,
) -> LifecycleStatus | None:
    invalid_status = _invalid_finite_decision_status(
        state=state,
        request=request,
        result=result,
        invalid_reason=invalid_reason,
    )
    if invalid_status is not None:
        return invalid_status
    payload = _payload_object(result.payload)
    request_payload = _payload_object(request.payload)
    drift_field = _selected_target_drift_field(
        state=state,
        request=request,
        payload=payload,
        request_payload=request_payload,
        expected_decision_type=expected_decision_type,
        expected_submission_kind=expected_submission_kind,
        expected_phase=expected_phase,
    )
    if drift_field is None:
        return None
    return LifecycleStatus.invalid(
        stage=state.stage,
        message="Catalog selected-target result drifted.",
        payload=validate_json_value({"invalid_reason": invalid_reason, "field": drift_field}),
    )


def _selected_target_drift_field(
    *,
    state: GameState,
    request: DecisionRequest,
    payload: Mapping[str, object],
    request_payload: Mapping[str, object],
    expected_decision_type: str,
    expected_submission_kind: str,
    expected_phase: BattlePhase,
) -> str | None:
    if request.decision_type != expected_decision_type:
        return "request_decision_type"
    if state.current_battle_phase is not expected_phase:
        return "state_phase"
    if _payload_string(payload, key="submission_kind") != expected_submission_kind:
        return "submission_kind"
    for key in (
        "hook_id",
        "game_id",
        "battle_round",
        "phase",
        "active_player_id",
        "player_id",
        "catalog_record_id",
        "source_rule_id",
        "source_unit_instance_id",
        "selection_clause_id",
    ):
        if payload.get(key) != request_payload.get(key):
            return key
    if payload.get("game_id") != state.game_id:
        return "game_id"
    if payload.get("battle_round") != state.battle_round:
        return "battle_round"
    if payload.get("phase") != expected_phase.value:
        return "phase"
    if payload.get("active_player_id") != state.active_player_id:
        return "active_player_id"
    selected = _selected_payload(payload)
    selected_target_id = _payload_string(selected, key="target_unit_instance_id")
    available_target_ids = _payload_string_tuple(
        request_payload,
        key="available_target_unit_instance_ids",
    )
    if selected_target_id not in available_target_ids:
        return "target_unit_instance_id"
    if state.battlefield_state is None:
        return "battlefield_state"
    if state.battlefield_state.unit_placement_or_none(selected_target_id) is None:
        return "target_unit_instance_id"
    return None


def _invalid_finite_decision_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
    invalid_reason: str,
) -> LifecycleStatus | None:
    if result.request_id != request.request_id:
        return _invalid_status(state=state, invalid_reason=invalid_reason, field="request_id")
    if result.decision_type != request.decision_type:
        return _invalid_status(state=state, invalid_reason=invalid_reason, field="decision_type")
    if result.actor_id != request.actor_id:
        return _invalid_status(state=state, invalid_reason=invalid_reason, field="actor_id")
    option_payload_by_id = {option.option_id: option.payload for option in request.options}
    selected_payload = option_payload_by_id.get(result.selected_option_id)
    if selected_payload is None:
        return _invalid_status(
            state=state,
            invalid_reason=invalid_reason,
            field="selected_option_id",
        )
    if result.payload != selected_payload:
        return _invalid_status(state=state, invalid_reason=invalid_reason, field="payload")
    return None


def _invalid_status(*, state: GameState, invalid_reason: str, field: str) -> LifecycleStatus:
    return LifecycleStatus.invalid(
        stage=state.stage,
        message="Catalog selected-target result is invalid.",
        payload=validate_json_value({"invalid_reason": invalid_reason, "field": field}),
    )


def _selected_target_option_id(
    *,
    record: AbilityCatalogRecord,
    unit: UnitInstance,
    source_model_instance_id: str | None,
    selection_clause: RuleClause,
    target_unit_instance_id: str,
    attack_sequence_completed_event_id: str | None,
) -> str:
    parts = [
        "catalog-ir",
        "selected-target",
        record.record_id,
        unit.unit_instance_id,
        "model",
        "unit" if source_model_instance_id is None else source_model_instance_id,
        selection_clause.clause_id,
    ]
    if attack_sequence_completed_event_id is not None:
        parts.append(attack_sequence_completed_event_id)
    parts.extend(("target", target_unit_instance_id))
    return ":".join(parts)


def _selected_target_option_selection_payload(
    option: _SelectedTargetOption,
) -> dict[str, JsonValue]:
    return {
        "option_id": option.option_id,
        "target_unit_instance_id": option.target_unit_instance_id,
    }


def _post_shoot_group_key(group: _SelectedTargetGroup) -> tuple[str, str, str, str, str]:
    if group.attack_sequence is None or group.attack_sequence_completed_event_id is None:
        raise GameLifecycleError("Catalog post-shoot group missing attack sequence.")
    return (
        group.attack_sequence_completed_event_id,
        group.attack_sequence.sequence_id,
        group.record.record_id,
        group.unit.unit_instance_id,
        group.selection_clause.clause_id,
    )


def _resolved_post_shoot_target_effect_group_keys(
    decisions: DecisionController,
) -> frozenset[tuple[str, str, str, str, str]]:
    keys: set[tuple[str, str, str, str, str]] = set()
    for event in decisions.event_log.records:
        if event.event_type != CATALOG_POST_SHOOT_HIT_TARGET_EFFECT_SELECTED_EVENT:
            continue
        payload = event.payload
        if not isinstance(payload, dict):
            raise GameLifecycleError("Catalog post-shoot selected event payload is malformed.")
        payload_object = cast(dict[str, object], payload)
        keys.add(
            (
                _payload_string(payload_object, key="attack_sequence_completed_event_id"),
                _payload_string(payload_object, key="attack_sequence_id"),
                _payload_string(payload_object, key="catalog_record_id"),
                _payload_string(payload_object, key="source_unit_instance_id"),
                _payload_string(payload_object, key="selection_clause_id"),
            )
        )
    return frozenset(keys)


def _validate_option(value: object) -> _SelectedTargetOption:
    if type(value) is not _SelectedTargetOption:
        raise GameLifecycleError("Catalog selected-target option is invalid.")
    return value
