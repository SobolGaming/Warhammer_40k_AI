from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import TYPE_CHECKING

from warhammer40k_core.core.dice import RerollComponentSelectionPolicy, RerollPermission
from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.core.weapon_profiles import WeaponKeyword, WeaponProfile
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.battle_round_hooks import (
    SELECT_FACTION_RULE_BATTLE_ROUND_OPTION_DECISION_TYPE,
    BattleRoundStartHookBinding,
    BattleRoundStartRequestContext,
    BattleRoundStartResultContext,
)
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
    PlacementError,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.charge_declaration_hooks import (
    ChargeDeclarationContext,
    ChargeDeclarationGrant,
    ChargeDeclarationHookBinding,
)
from warhammer40k_core.engine.decision_request import DecisionError, DecisionOption, DecisionRequest
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentContribution
from warhammer40k_core.engine.fall_back_hooks import (
    FallBackEligibilityContext,
    FallBackEligibilityGrant,
    FallBackEligibilityHookBinding,
)
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlContext,
    ObjectiveControlRecord,
    ObjectiveControlResult,
    ObjectiveControlTiming,
    resolve_objective_control,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.runtime_modifiers import (
    RuntimeModifierRegistry,
    WeaponProfileModifierBinding,
    WeaponProfileModifierContext,
    WoundRollModifierBinding,
    WoundRollModifierContext,
)
from warhammer40k_core.engine.source_backed_rerolls import (
    SOURCE_BACKED_REROLL_PERMISSION_EFFECT_KIND,
    source_backed_reroll_permission_effect_payload,
    source_payload_from_reroll_effect_payload,
)
from warhammer40k_core.engine.sticky_objective_control import (
    PhaseEndObjectiveControlContext,
    PhaseEndObjectiveControlHookBinding,
    StickyObjectiveControlState,
    apply_sticky_objective_control,
)
from warhammer40k_core.engine.target_restriction_hooks import (
    ChargeTargetRestrictionContext,
    ChargeTargetRestrictionHookBinding,
    TargetRestriction,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry.volume import Model as GeometryModel

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


CONTRIBUTION_ID = "warhammer_40000_11th:black_templars:army_rule:templar_vows"
HOOK_ID = "warhammer_40000_11th:black_templars:army_rule:templar_vows"
ABHOR_CHARGE_DECLARATION_HOOK_ID = f"{HOOK_ID}:abhor_the_witch:charge-declaration"
ABHOR_CHARGE_TARGET_RESTRICTION_HOOK_ID = f"{HOOK_ID}:abhor_the_witch:charge-targets"
ABHOR_MELEE_PRECISION_MODIFIER_ID = f"{HOOK_ID}:abhor_the_witch:melee-precision"
ACCEPT_ANY_CHALLENGE_WOUND_MODIFIER_ID = f"{HOOK_ID}:accept_any_challenge:wound-roll"
SUFFER_FALL_BACK_ELIGIBILITY_HOOK_ID = f"{HOOK_ID}:suffer_not_the_unclean:fall-back"
UPHOLD_OBJECTIVE_CONTROL_HOOK_ID = f"{HOOK_ID}:uphold_the_honour:objective-control"
SOURCE_RULE_ID = "phase17f:phase17e:black-templars:army-rule"
BLACK_TEMPLARS_FACTION_ID = "black-templars"
BLACK_TEMPLARS_FACTION_KEYWORD = "BLACK TEMPLARS"
ADEPTUS_ASTARTES_KEYWORD = "ADEPTUS ASTARTES"
PSYKER_KEYWORD = "PSYKER"
TEMPLAR_VOWS_EFFECT_KIND = "black_templars_templar_vows"
ABHOR_CHARGE_EFFECT_KIND = "black_templars_abhor_the_witch_charge"
UPHOLD_STICKY_EFFECT_KIND = "black_templars_uphold_the_honour_objective_control"
ABHOR_CHARGE_PSYKER_RANGE_INCHES = 12.0


class TemplarVow(StrEnum):
    ABHOR_THE_WITCH = "abhor_the_witch"
    ACCEPT_ANY_CHALLENGE = "accept_any_challenge"
    SUFFER_NOT_THE_UNCLEAN = "suffer_not_the_unclean"
    UPHOLD_THE_HONOUR = "uphold_the_honour"


@dataclass(frozen=True, slots=True)
class TemplarVowDefinition:
    vow: TemplarVow
    label: str
    effect_summary: str

    def __post_init__(self) -> None:
        if type(self.vow) is not TemplarVow:
            raise GameLifecycleError("Templar Vow definition vow drift.")
        if type(self.label) is not str or not self.label.strip():
            raise GameLifecycleError("Templar Vow definition label must be non-empty.")
        if type(self.effect_summary) is not str or not self.effect_summary.strip():
            raise GameLifecycleError("Templar Vow definition summary must be non-empty.")


TEMPLAR_VOW_DEFINITIONS: tuple[TemplarVowDefinition, ...] = (
    TemplarVowDefinition(
        vow=TemplarVow.ABHOR_THE_WITCH,
        label="Abhor the Witch, Destroy the Witch",
        effect_summary=(
            "Melee attacks targeting PSYKER units have Precision; a charge can be declared "
            "against nearby PSYKER units to reroll the charge and require a reachable PSYKER "
            "target."
        ),
    ),
    TemplarVowDefinition(
        vow=TemplarVow.ACCEPT_ANY_CHALLENGE,
        label="Accept Any Challenge, No Matter the Odds",
        effect_summary=(
            "Melee attacks add 1 to wound rolls when Strength is not greater than Toughness."
        ),
    ),
    TemplarVowDefinition(
        vow=TemplarVow.SUFFER_NOT_THE_UNCLEAN,
        label="Suffer Not the Unclean to Live",
        effect_summary="Eligible units can declare a charge in a turn in which they Fell Back.",
    ),
    TemplarVowDefinition(
        vow=TemplarVow.UPHOLD_THE_HONOUR,
        label="Uphold the Honour of the Emperor",
        effect_summary=(
            "Eligible units retain control of objectives controlled at Command phase end."
        ),
    ),
)
_VOW_DEFINITIONS_BY_VOW = {definition.vow: definition for definition in TEMPLAR_VOW_DEFINITIONS}


def runtime_contribution() -> RuntimeContentContribution:
    return RuntimeContentContribution(
        contribution_id=CONTRIBUTION_ID,
        battle_round_start_hook_bindings=(
            BattleRoundStartHookBinding(
                hook_id=HOOK_ID,
                source_id=SOURCE_RULE_ID,
                request_handler=templar_vow_selection_request,
                result_handler=apply_templar_vow_selection_result,
            ),
        ),
        charge_declaration_hook_bindings=(
            ChargeDeclarationHookBinding(
                hook_id=ABHOR_CHARGE_DECLARATION_HOOK_ID,
                source_id=SOURCE_RULE_ID,
                handler=abhor_charge_declaration_grant,
            ),
        ),
        charge_target_restriction_hook_bindings=(
            ChargeTargetRestrictionHookBinding(
                hook_id=ABHOR_CHARGE_TARGET_RESTRICTION_HOOK_ID,
                source_id=SOURCE_RULE_ID,
                handler=abhor_charge_target_restriction,
            ),
        ),
        fall_back_hook_bindings=(
            FallBackEligibilityHookBinding(
                hook_id=SUFFER_FALL_BACK_ELIGIBILITY_HOOK_ID,
                source_id=SOURCE_RULE_ID,
                handler=suffer_not_the_unclean_fall_back_eligibility,
            ),
        ),
        phase_end_objective_control_hook_bindings=(
            PhaseEndObjectiveControlHookBinding(
                hook_id=UPHOLD_OBJECTIVE_CONTROL_HOOK_ID,
                source_id=SOURCE_RULE_ID,
                handler=uphold_objective_control_states,
            ),
        ),
        wound_roll_modifier_bindings=(
            WoundRollModifierBinding(
                modifier_id=ACCEPT_ANY_CHALLENGE_WOUND_MODIFIER_ID,
                source_id=SOURCE_RULE_ID,
                handler=accept_any_challenge_wound_roll_modifier,
            ),
        ),
        weapon_profile_modifier_bindings=(
            WeaponProfileModifierBinding(
                modifier_id=ABHOR_MELEE_PRECISION_MODIFIER_ID,
                source_id=SOURCE_RULE_ID,
                handler=abhor_weapon_profile_modifier,
            ),
        ),
    )


def templar_vow_selection_request(
    context: BattleRoundStartRequestContext,
) -> DecisionRequest | None:
    if type(context) is not BattleRoundStartRequestContext:
        raise GameLifecycleError("Templar Vows requires request context.")
    for army in _black_templars_armies(context.state):
        if _vow_selection_recorded_for_player(context.state, player_id=army.player_id):
            continue
        target_unit_ids = _eligible_templar_vow_unit_ids_for_army(army)
        if not target_unit_ids:
            continue
        return DecisionRequest(
            request_id=context.state.next_decision_request_id(),
            decision_type=SELECT_FACTION_RULE_BATTLE_ROUND_OPTION_DECISION_TYPE,
            actor_id=army.player_id,
            payload=validate_json_value(
                {
                    "game_id": context.state.game_id,
                    "battle_round": context.state.battle_round,
                    "phase": BattlePhase.COMMAND.value,
                    "faction_id": BLACK_TEMPLARS_FACTION_ID,
                    "source_rule_id": SOURCE_RULE_ID,
                    "hook_id": HOOK_ID,
                    "effect_kind": TEMPLAR_VOWS_EFFECT_KIND,
                    "target_unit_instance_ids": list(target_unit_ids),
                }
            ),
            options=templar_vow_selection_options(
                player_id=army.player_id,
                battle_round=context.state.battle_round,
            ),
        )
    return None


def apply_templar_vow_selection_result(context: BattleRoundStartResultContext) -> bool:
    if type(context) is not BattleRoundStartResultContext:
        raise GameLifecycleError("Templar Vows requires result context.")
    if context.request.decision_type != SELECT_FACTION_RULE_BATTLE_ROUND_OPTION_DECISION_TYPE:
        return False
    request_payload = _payload_object(context.request.payload)
    if request_payload.get("hook_id") != HOOK_ID:
        return False
    result = context.result
    if result.actor_id is None:
        raise GameLifecycleError("Templar Vows selection requires an actor.")
    player_id = result.actor_id
    army = _black_templars_army_for_player(context.state, player_id=player_id)
    if army is None:
        raise GameLifecycleError("Templar Vows actor does not own Black Templars.")
    if _vow_selection_recorded_for_player(context.state, player_id=player_id):
        raise GameLifecycleError("Templar Vows selection is already recorded.")
    try:
        expected_option = context.request.option_by_id(result.selected_option_id)
    except DecisionError as exc:
        raise GameLifecycleError("Templar Vows selected option is not available.") from exc
    if result.payload != expected_option.payload:
        raise GameLifecycleError("Templar Vows selected option payload drift.")
    payload = _payload_object(result.payload)
    vow = _templar_vow_from_token(_payload_string(payload, key="selected_vow_id"))
    target_unit_ids = _eligible_templar_vow_unit_ids_for_army(army)
    if not target_unit_ids:
        raise GameLifecycleError("Templar Vows selection has no eligible units.")
    definition = _VOW_DEFINITIONS_BY_VOW[vow]
    effect = PersistingEffect(
        effect_id=f"{HOOK_ID}:{player_id}:battle:active-vow",
        source_rule_id=SOURCE_RULE_ID,
        owner_player_id=player_id,
        target_unit_instance_ids=target_unit_ids,
        started_battle_round=context.state.battle_round,
        started_phase=BattlePhaseKind.COMMAND,
        expiration=EffectExpiration.end_of_battle(),
        effect_payload=validate_json_value(
            {
                "effect_kind": TEMPLAR_VOWS_EFFECT_KIND,
                "battle_round": context.state.battle_round,
                "phase": BattlePhase.COMMAND.value,
                "player_id": player_id,
                "faction_id": BLACK_TEMPLARS_FACTION_ID,
                "source_rule_id": SOURCE_RULE_ID,
                "hook_id": HOOK_ID,
                "selected_vow_id": vow.value,
                "selected_vow_label": definition.label,
                "selected_option_id": result.selected_option_id,
                "request_id": context.request.request_id,
                "result_id": result.result_id,
            }
        ),
    )
    context.state.record_persisting_effect(effect)
    context.decisions.event_log.append(
        "black_templars_templar_vow_selected",
        validate_json_value(
            {
                "game_id": context.state.game_id,
                "battle_round": context.state.battle_round,
                "phase": BattlePhase.COMMAND.value,
                "player_id": player_id,
                "source_rule_id": SOURCE_RULE_ID,
                "hook_id": HOOK_ID,
                "selected_vow_id": vow.value,
                "persisting_effect": effect.to_payload(),
            }
        ),
    )
    return True


def templar_vow_selection_options(
    *,
    player_id: str,
    battle_round: int,
) -> tuple[DecisionOption, ...]:
    requested_player_id = _validate_identifier("player_id", player_id)
    if type(battle_round) is not int or battle_round <= 0:
        raise GameLifecycleError("Templar Vows options require positive battle_round.")
    return tuple(
        DecisionOption(
            option_id=f"black_templars:templar_vows:{definition.vow.value}",
            label=definition.label,
            payload=validate_json_value(
                {
                    "submission_kind": "select_black_templars_templar_vow",
                    "player_id": requested_player_id,
                    "battle_round": battle_round,
                    "faction_id": BLACK_TEMPLARS_FACTION_ID,
                    "source_rule_id": SOURCE_RULE_ID,
                    "hook_id": HOOK_ID,
                    "effect_kind": TEMPLAR_VOWS_EFFECT_KIND,
                    "selected_vow_id": definition.vow.value,
                    "selected_vow_label": definition.label,
                    "effect_summary": definition.effect_summary,
                }
            ),
        )
        for definition in TEMPLAR_VOW_DEFINITIONS
    )


def active_templar_vow_for_player(
    state: GameState,
    *,
    player_id: str,
) -> TemplarVow | None:
    _validate_game_state(state)
    requested_player_id = _validate_identifier("player_id", player_id)
    matching = _active_vow_effects_for_player(state, player_id=requested_player_id)
    if not matching:
        return None
    payload = _payload_object(matching[0].effect_payload)
    return _templar_vow_from_token(_payload_string(payload, key="selected_vow_id"))


def unit_has_active_templar_vow(
    state: GameState,
    *,
    unit_instance_id: str,
    vow: TemplarVow,
) -> bool:
    _validate_game_state(state)
    requested_vow = _templar_vow_from_token(vow)
    unit, army = _unit_and_army_by_id(state, unit_instance_id=unit_instance_id)
    if not _unit_has_templar_vows(unit):
        return False
    return active_templar_vow_for_player(state, player_id=army.player_id) is requested_vow


def abhor_weapon_profile_modifier(context: WeaponProfileModifierContext) -> WeaponProfile:
    if type(context) is not WeaponProfileModifierContext:
        raise GameLifecycleError("Abhor the Witch weapon modifier requires context.")
    if context.source_phase is not BattlePhase.FIGHT:
        return context.weapon_profile
    if not unit_has_active_templar_vow(
        context.state,
        unit_instance_id=context.attacking_unit_instance_id,
        vow=TemplarVow.ABHOR_THE_WITCH,
    ):
        return context.weapon_profile
    if not _target_unit_has_keyword(
        context.state,
        unit_instance_id=context.target_unit_instance_id,
        keyword=PSYKER_KEYWORD,
    ):
        return context.weapon_profile
    return _profile_with_keyword(context.weapon_profile, keyword=WeaponKeyword.PRECISION)


def accept_any_challenge_wound_roll_modifier(context: WoundRollModifierContext) -> int:
    if type(context) is not WoundRollModifierContext:
        raise GameLifecycleError("Accept Any Challenge wound modifier requires context.")
    if context.source_phase is not BattlePhase.FIGHT:
        return 0
    if context.strength > context.toughness:
        return 0
    if not unit_has_active_templar_vow(
        context.state,
        unit_instance_id=context.attacking_unit_instance_id,
        vow=TemplarVow.ACCEPT_ANY_CHALLENGE,
    ):
        return 0
    return 1


def abhor_charge_declaration_grant(
    context: ChargeDeclarationContext,
) -> ChargeDeclarationGrant | None:
    if type(context) is not ChargeDeclarationContext:
        raise GameLifecycleError("Abhor the Witch charge declaration requires context.")
    if not unit_has_active_templar_vow(
        context.state,
        unit_instance_id=context.unit_instance_id,
        vow=TemplarVow.ABHOR_THE_WITCH,
    ):
        return None
    psyker_unit_ids = _enemy_psyker_unit_ids_within_abhor_range(
        state=context.state,
        player_id=context.player_id,
        unit_instance_id=context.unit_instance_id,
    )
    if not psyker_unit_ids:
        return None
    source_payload = validate_json_value(
        {
            "effect_kind": ABHOR_CHARGE_EFFECT_KIND,
            "battle_round": context.battle_round,
            "phase": BattlePhase.CHARGE.value,
            "player_id": context.player_id,
            "unit_instance_id": context.unit_instance_id,
            "source_rule_id": SOURCE_RULE_ID,
            "hook_id": ABHOR_CHARGE_DECLARATION_HOOK_ID,
            "selection_request_id": context.selection_request_id,
            "selection_result_id": context.selection_result_id,
            "psyker_unit_instance_ids_within_12": list(psyker_unit_ids),
            "charge_move_required_target_unit_instance_ids": list(psyker_unit_ids),
            "charge_move_required_target_kind": "psyker",
        }
    )
    permission = RerollPermission(
        source_id=(
            f"{ABHOR_CHARGE_DECLARATION_HOOK_ID}:{context.unit_instance_id}:"
            f"round-{context.battle_round:02d}:{context.selection_result_id}"
        ),
        timing_window="after_charge_roll",
        owning_player_id=context.player_id,
        eligible_roll_type="charge_roll",
        component_selection_policy=RerollComponentSelectionPolicy.WHOLE_ROLL,
    )
    return ChargeDeclarationGrant(
        hook_id=ABHOR_CHARGE_DECLARATION_HOOK_ID,
        source_id=SOURCE_RULE_ID,
        label="Abhor the Witch, Destroy the Witch",
        replay_payload=source_payload,
        unit_effect_payload=source_backed_reroll_permission_effect_payload(
            target_unit_instance_ids=(context.unit_instance_id,),
            permission=permission,
            source_payload=source_payload,
        ),
        unit_effect_expiration="end_phase",
    )


def abhor_charge_target_restriction(
    context: ChargeTargetRestrictionContext,
) -> TargetRestriction | None:
    if type(context) is not ChargeTargetRestrictionContext:
        raise GameLifecycleError("Abhor the Witch charge restriction requires context.")
    if (
        _active_abhor_charge_source_payload_for_unit(
            context.state,
            player_id=context.player_id,
            unit_instance_id=context.charging_unit_instance_id,
        )
        is None
    ):
        return None
    if _target_unit_has_keyword(
        context.state,
        unit_instance_id=context.target_unit_instance_id,
        keyword=PSYKER_KEYWORD,
    ):
        return None
    return TargetRestriction(
        hook_id=ABHOR_CHARGE_TARGET_RESTRICTION_HOOK_ID,
        source_id=SOURCE_RULE_ID,
        violation_code="black_templars_abhor_charge_requires_psyker_target",
        message="Abhor the Witch charge must target a PSYKER unit.",
        replay_payload=validate_json_value(
            {
                "effect_kind": ABHOR_CHARGE_EFFECT_KIND,
                "battle_round": context.battle_round,
                "player_id": context.player_id,
                "charging_unit_instance_id": context.charging_unit_instance_id,
                "target_unit_instance_id": context.target_unit_instance_id,
                "required_keyword": PSYKER_KEYWORD,
            }
        ),
    )


def suffer_not_the_unclean_fall_back_eligibility(
    context: FallBackEligibilityContext,
) -> FallBackEligibilityGrant | None:
    if type(context) is not FallBackEligibilityContext:
        raise GameLifecycleError("Suffer Not the Unclean Fall Back eligibility requires context.")
    if not unit_has_active_templar_vow(
        context.state,
        unit_instance_id=context.unit_instance_id,
        vow=TemplarVow.SUFFER_NOT_THE_UNCLEAN,
    ):
        return None
    return FallBackEligibilityGrant(
        hook_id=SUFFER_FALL_BACK_ELIGIBILITY_HOOK_ID,
        source_id=SOURCE_RULE_ID,
        can_shoot=False,
        can_declare_charge=True,
        replay_payload=validate_json_value(
            {
                "effect_kind": TEMPLAR_VOWS_EFFECT_KIND,
                "selected_vow_id": TemplarVow.SUFFER_NOT_THE_UNCLEAN.value,
                "battle_round": context.battle_round,
                "player_id": context.player_id,
                "unit_instance_id": context.unit_instance_id,
                "can_declare_charge_after_fall_back": True,
            }
        ),
    )


def uphold_objective_control_states(
    context: PhaseEndObjectiveControlContext,
) -> tuple[StickyObjectiveControlState, ...]:
    if type(context) is not PhaseEndObjectiveControlContext:
        raise GameLifecycleError("Uphold the Honour objective control requires context.")
    if context.completed_phase is not BattlePhase.COMMAND:
        return ()
    record = _objective_control_record_for_state(
        state_context=context.state,
        completed_phase=context.completed_phase,
        runtime_modifier_registry=context.runtime_modifier_registry,
    )
    if record is None:
        return ()
    states: list[StickyObjectiveControlState] = []
    active_player_id = _active_player_id(context)
    for army in _black_templars_armies(context.state):
        if army.player_id != active_player_id:
            continue
        if active_templar_vow_for_player(context.state, player_id=army.player_id) is not (
            TemplarVow.UPHOLD_THE_HONOUR
        ):
            continue
        states.extend(_uphold_states_for_army(context=context, army=army, record=record))
    return tuple(sorted(states, key=lambda state: state.state_id))


def _uphold_states_for_army(
    *,
    context: PhaseEndObjectiveControlContext,
    army: ArmyDefinition,
    record: ObjectiveControlRecord,
) -> tuple[StickyObjectiveControlState, ...]:
    eligible_unit_ids = set(_eligible_templar_vow_unit_ids_for_army(army))
    if not eligible_unit_ids:
        return ()
    states: list[StickyObjectiveControlState] = []
    seen_state_keys: set[tuple[str, str]] = set()
    for result in record.results:
        if result.controlled_by_player_id != army.player_id:
            continue
        for unit_instance_id in _result_eligible_unit_ids_in_range(
            result=result,
            eligible_unit_ids=eligible_unit_ids,
        ):
            state_key = (result.objective_id, unit_instance_id)
            if state_key in seen_state_keys:
                continue
            seen_state_keys.add(state_key)
            states.append(
                StickyObjectiveControlState(
                    state_id=(
                        f"black-templars-uphold:{context.state.game_id}:"
                        f"round-{context.state.battle_round:02d}:"
                        f"{army.player_id}:{result.objective_id}:{unit_instance_id}"
                    ),
                    game_id=context.state.game_id,
                    player_id=army.player_id,
                    objective_id=result.objective_id,
                    source_rule_id=SOURCE_RULE_ID,
                    source_event_id=(
                        f"black-templars-uphold-phase-end:{context.state.game_id}:"
                        f"round-{context.state.battle_round:02d}:"
                        f"{army.player_id}:{context.completed_phase.value}"
                    ),
                    battle_round=context.state.battle_round,
                    phase=context.completed_phase.value,
                    active_player_id=army.player_id,
                    originating_unit_instance_id=unit_instance_id,
                    destroyed_unit_instance_id=unit_instance_id,
                    replay_payload=validate_json_value(
                        {
                            "effect_kind": UPHOLD_STICKY_EFFECT_KIND,
                            "selected_vow_id": TemplarVow.UPHOLD_THE_HONOUR.value,
                            "objective_id": result.objective_id,
                            "originating_unit_instance_id": unit_instance_id,
                            "controlling_player_id": army.player_id,
                        }
                    ),
                )
            )
    return tuple(sorted(states, key=lambda state: state.state_id))


def _objective_control_record_for_state(
    *,
    state_context: object,
    completed_phase: BattlePhase,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> ObjectiveControlRecord | None:
    from warhammer40k_core.engine.game_state import GameState

    if type(state_context) is not GameState:
        raise GameLifecycleError("Uphold objective control requires GameState.")
    if type(completed_phase) is not BattlePhase:
        raise GameLifecycleError("Uphold objective control requires BattlePhase.")
    if type(runtime_modifier_registry) is not RuntimeModifierRegistry:
        raise GameLifecycleError("Uphold objective control requires RuntimeModifierRegistry.")
    if state_context.mission_setup is None or state_context.battlefield_state is None:
        return None
    record = resolve_objective_control(
        ObjectiveControlContext.from_game_state(
            state_context,
            timing=ObjectiveControlTiming.PHASE_END,
            phase=completed_phase,
            ruleset_descriptor=state_context.runtime_ruleset_descriptor(),
            runtime_modifier_registry=runtime_modifier_registry,
        )
    )
    return apply_sticky_objective_control(
        record=record,
        states=tuple(state_context.sticky_objective_control_states),
    )


def _result_eligible_unit_ids_in_range(
    *,
    result: ObjectiveControlResult,
    eligible_unit_ids: set[str],
) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                contribution.unit_instance_id
                for contribution in result.contributors
                if contribution.unit_instance_id in eligible_unit_ids
            }
        )
    )


def _vow_selection_recorded_for_player(
    state: GameState,
    *,
    player_id: str,
) -> bool:
    return active_templar_vow_for_player(state, player_id=player_id) is not None


def _active_vow_effects_for_player(
    state: GameState,
    *,
    player_id: str,
) -> tuple[PersistingEffect, ...]:
    requested_player_id = _validate_identifier("player_id", player_id)
    matching: list[PersistingEffect] = []
    for effect in state.persisting_effects:
        if effect.owner_player_id != requested_player_id:
            continue
        if effect.source_rule_id != SOURCE_RULE_ID:
            continue
        payload = _payload_object(effect.effect_payload)
        if payload.get("effect_kind") != TEMPLAR_VOWS_EFFECT_KIND:
            continue
        matching.append(effect)
    if len(matching) > 1:
        raise GameLifecycleError("Templar Vows lookup found multiple active effects.")
    return tuple(matching)


def _active_abhor_charge_source_payload_for_unit(
    state: GameState,
    *,
    player_id: str,
    unit_instance_id: str,
) -> dict[str, JsonValue] | None:
    requested_player_id = _validate_identifier("player_id", player_id)
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    matching: list[dict[str, JsonValue]] = []
    for effect in state.persisting_effects_for_unit(requested_unit_id):
        if effect.owner_player_id != requested_player_id:
            continue
        if effect.source_rule_id != SOURCE_RULE_ID:
            continue
        payload = effect.effect_payload
        if not isinstance(payload, dict):
            continue
        if payload.get("effect_kind") != SOURCE_BACKED_REROLL_PERMISSION_EFFECT_KIND:
            continue
        source_payload = source_payload_from_reroll_effect_payload(payload)
        if source_payload.get("effect_kind") != ABHOR_CHARGE_EFFECT_KIND:
            continue
        matching.append(source_payload)
    if len(matching) > 1:
        raise GameLifecycleError("Abhor the Witch lookup found multiple active charge effects.")
    return matching[0] if matching else None


def _enemy_psyker_unit_ids_within_abhor_range(
    *,
    state: GameState,
    player_id: str,
    unit_instance_id: str,
) -> tuple[str, ...]:
    requested_player_id = _validate_identifier("player_id", player_id)
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    _unit_and_army_by_id(state, unit_instance_id=requested_unit_id)
    unit_ids: list[str] = []
    for army in state.army_definitions:
        if army.player_id == requested_player_id:
            continue
        for unit in army.units:
            if not _unit_has_keyword(unit, PSYKER_KEYWORD):
                continue
            if not _unit_is_placed(state, unit_instance_id=unit.unit_instance_id):
                continue
            if (
                _closest_unit_distance_inches(
                    state=state,
                    source_unit_instance_id=requested_unit_id,
                    target_unit_instance_id=unit.unit_instance_id,
                )
                <= ABHOR_CHARGE_PSYKER_RANGE_INCHES
            ):
                unit_ids.append(unit.unit_instance_id)
    return tuple(sorted(unit_ids))


def _closest_unit_distance_inches(
    *,
    state: GameState,
    source_unit_instance_id: str,
    target_unit_instance_id: str,
) -> float:
    scenario = _battlefield_scenario(state)
    source_models = _geometry_models_for_unit(
        scenario=scenario,
        unit_instance_id=source_unit_instance_id,
    )
    target_models = _geometry_models_for_unit(
        scenario=scenario,
        unit_instance_id=target_unit_instance_id,
    )
    if not source_models or not target_models:
        raise GameLifecycleError("Abhor the Witch charge distance requires placed models.")
    return min(
        source_model.range_to(target_model)
        for source_model in source_models
        for target_model in target_models
    )


def _geometry_models_for_unit(
    *,
    scenario: BattlefieldScenario,
    unit_instance_id: str,
) -> tuple[GeometryModel, ...]:
    unit_placement = scenario.battlefield_state.unit_placement_by_id(unit_instance_id)
    return tuple(
        geometry_model_for_placement(
            model=scenario.model_instance_for_placement(placement),
            placement=placement,
        )
        for placement in unit_placement.model_placements
    )


def _battlefield_scenario(state: GameState) -> BattlefieldScenario:
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Black Templars army rule requires battlefield_state.")
    try:
        return BattlefieldScenario(
            armies=tuple(state.army_definitions),
            battlefield_state=battlefield_state,
        )
    except PlacementError as exc:
        raise GameLifecycleError("Black Templars battlefield scenario is invalid.") from exc


def _unit_is_placed(state: GameState, *, unit_instance_id: str) -> bool:
    if state.battlefield_state is None:
        raise GameLifecycleError("Black Templars placement lookup requires battlefield_state.")
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    return any(
        placement.unit_instance_id == requested_unit_id
        for placed_army in state.battlefield_state.placed_armies
        for placement in placed_army.unit_placements
    )


def _eligible_templar_vow_unit_ids_for_army(army: ArmyDefinition) -> tuple[str, ...]:
    if type(army) is not ArmyDefinition:
        raise GameLifecycleError("Templar Vows requires an ArmyDefinition.")
    return tuple(unit.unit_instance_id for unit in army.units if _unit_has_templar_vows(unit))


def _unit_has_templar_vows(unit: UnitInstance) -> bool:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("Templar Vows requires a UnitInstance.")
    return _unit_has_keyword(unit, ADEPTUS_ASTARTES_KEYWORD) or _unit_has_keyword(
        unit,
        BLACK_TEMPLARS_FACTION_KEYWORD,
    )


def _target_unit_has_keyword(state: GameState, *, unit_instance_id: str, keyword: str) -> bool:
    unit, _army = _unit_and_army_by_id(state, unit_instance_id=unit_instance_id)
    return _unit_has_keyword(unit, keyword)


def _unit_has_keyword(unit: UnitInstance, keyword: str) -> bool:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("Black Templars keyword check requires UnitInstance.")
    requested_keyword = _canonical_keyword(keyword)
    return any(
        _canonical_keyword(stored_keyword) == requested_keyword
        for stored_keyword in (*unit.keywords, *unit.faction_keywords)
    )


def _black_templars_armies(state: GameState) -> tuple[ArmyDefinition, ...]:
    _validate_game_state(state)
    return tuple(
        army
        for army in state.army_definitions
        if army.detachment_selection.faction_id == BLACK_TEMPLARS_FACTION_ID
    )


def _black_templars_army_for_player(
    state: GameState,
    *,
    player_id: str,
) -> ArmyDefinition | None:
    requested_player_id = _validate_identifier("player_id", player_id)
    for army in _black_templars_armies(state):
        if army.player_id == requested_player_id:
            return army
    return None


def _unit_and_army_by_id(
    state: GameState,
    *,
    unit_instance_id: str,
) -> tuple[UnitInstance, ArmyDefinition]:
    _validate_game_state(state)
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for army in state.army_definitions:
        for unit in army.units:
            if unit.unit_instance_id == requested_unit_id:
                return unit, army
    raise GameLifecycleError("Black Templars unit_instance_id was not found.")


def _profile_with_keyword(profile: WeaponProfile, *, keyword: WeaponKeyword) -> WeaponProfile:
    if type(profile) is not WeaponProfile:
        raise GameLifecycleError("Black Templars weapon modifier requires WeaponProfile.")
    keywords = profile.keywords
    if keyword not in keywords:
        keywords = (*keywords, keyword)
    source_ids = profile.source_ids
    if SOURCE_RULE_ID not in source_ids:
        source_ids = (*source_ids, SOURCE_RULE_ID)
    return replace(profile, keywords=keywords, source_ids=source_ids)


def _active_player_id(context: PhaseEndObjectiveControlContext) -> str:
    active_player_id = context.state.active_player_id
    if active_player_id is None:
        raise GameLifecycleError("Black Templars objective control requires an active player.")
    return active_player_id


def _templar_vow_from_token(token: object) -> TemplarVow:
    if type(token) is TemplarVow:
        return token
    if type(token) is not str:
        raise GameLifecycleError("Templar Vow token must be a string.")
    try:
        return TemplarVow(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported Templar Vow: {token}.") from exc


def _payload_object(payload: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(payload, dict):
        raise GameLifecycleError("Templar Vows payload must be an object.")
    return payload


def _payload_string(payload: dict[str, JsonValue], *, key: str) -> str:
    value = payload.get(key)
    return _validate_identifier(key, value)


def _validate_game_state(state: object) -> None:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Black Templars army rule requires GameState.")


_validate_identifier = IdentifierValidator(GameLifecycleError)


def _canonical_keyword(value: str) -> str:
    return _validate_identifier("keyword", value).upper().replace("_", " ")
