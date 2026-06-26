from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind, RulesetDescriptor
from warhammer40k_core.core.weapon_profiles import RangeProfileKind, WeaponKeyword, WeaponProfile
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.battlefield_state import BattlefieldScenario, PlacementError
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentContribution
from warhammer40k_core.engine.faction_rule_states import FactionRuleState
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, SetupStep
from warhammer40k_core.engine.phases.shooting import shooting_rules_unit_is_eligible_to_shoot
from warhammer40k_core.engine.rules_units import (
    RulesUnitView,
    rules_unit_id_for_unit_id,
    rules_unit_view_by_id,
)
from warhammer40k_core.engine.runtime_modifiers import (
    WeaponProfileModifierBinding,
    WeaponProfileModifierContext,
)
from warhammer40k_core.engine.shooting_phase_start_hooks import (
    SELECT_FACTION_RULE_SHOOTING_PHASE_START_OPTION_DECISION_TYPE,
    ShootingPhaseStartHookBinding,
    ShootingPhaseStartRequestContext,
    ShootingPhaseStartResultContext,
)
from warhammer40k_core.engine.shooting_targets import unit_has_line_of_sight_to_target
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


CONTRIBUTION_ID = "warhammer_40000_11th:tau_empire:army_rule:for_the_greater_good"
HOOK_ID = "warhammer_40000_11th:tau_empire:army_rule:for_the_greater_good"
WEAPON_PROFILE_MODIFIER_ID = f"{HOOK_ID}:weapon-profile"
SOURCE_RULE_ID = "phase17f:phase17e:tau-empire:army-rule"
TAU_EMPIRE_FACTION_ID = "tau-empire"
TAU_EMPIRE_FACTION_KEYWORD = "T'AU EMPIRE"
FOR_THE_GREATER_GOOD_ABILITY_NAME = "For the Greater Good"
MARKERLIGHT_KEYWORD = "MARKERLIGHT"
FORTIFICATION_KEYWORD = "FORTIFICATION"
FOR_THE_GREATER_GOOD_EFFECT_KIND = "tau_empire_for_the_greater_good_spotted"
FOR_THE_GREATER_GOOD_DONE_STATE_KIND = "tau_empire_for_the_greater_good_shooting_phase_done"
FOR_THE_GREATER_GOOD_SELECTION_KIND = "tau_empire_for_the_greater_good_mark"
FOR_THE_GREATER_GOOD_DONE_OPTION_ID = "tau-empire:for-the-greater-good:done"


@dataclass(frozen=True, slots=True)
class ForTheGreaterGoodMarkOption:
    observer_rules_unit: RulesUnitView
    spotted_rules_unit: RulesUnitView
    observer_has_markerlight: bool

    def __post_init__(self) -> None:
        if type(self.observer_rules_unit) is not RulesUnitView:
            raise GameLifecycleError("For the Greater Good option requires observer rules unit.")
        if type(self.spotted_rules_unit) is not RulesUnitView:
            raise GameLifecycleError("For the Greater Good option requires spotted rules unit.")
        if type(self.observer_has_markerlight) is not bool:
            raise GameLifecycleError("For the Greater Good markerlight flag must be bool.")


def runtime_contribution() -> RuntimeContentContribution:
    return RuntimeContentContribution(
        contribution_id=CONTRIBUTION_ID,
        shooting_phase_start_hook_bindings=(
            ShootingPhaseStartHookBinding(
                hook_id=HOOK_ID,
                source_id=SOURCE_RULE_ID,
                request_handler=for_the_greater_good_request,
                result_handler=apply_for_the_greater_good_result,
            ),
        ),
        weapon_profile_modifier_bindings=(
            WeaponProfileModifierBinding(
                modifier_id=WEAPON_PROFILE_MODIFIER_ID,
                source_id=SOURCE_RULE_ID,
                handler=for_the_greater_good_weapon_profile_modifier,
            ),
        ),
    )


def for_the_greater_good_request(
    context: ShootingPhaseStartRequestContext,
) -> DecisionRequest | None:
    if type(context) is not ShootingPhaseStartRequestContext:
        raise GameLifecycleError("For the Greater Good requires request context.")
    active_player_id = _active_player_id(context.state)
    army = _tau_empire_army_for_player(context.state, player_id=active_player_id)
    if army is None:
        return None
    if _for_the_greater_good_done_this_shooting_phase(
        context.state,
        player_id=army.player_id,
    ):
        return None

    marks = _eligible_for_the_greater_good_marks(context, army=army)
    if not marks:
        return None

    common_payload = _payload_object(
        validate_json_value(
            {
                "game_id": context.state.game_id,
                "battle_round": context.state.battle_round,
                "phase": BattlePhase.SHOOTING.value,
                "active_player_id": army.player_id,
                "player_id": army.player_id,
                "faction_id": TAU_EMPIRE_FACTION_ID,
                "source_rule_id": SOURCE_RULE_ID,
                "hook_id": HOOK_ID,
                "effect_kind": FOR_THE_GREATER_GOOD_EFFECT_KIND,
                "selection_kind": FOR_THE_GREATER_GOOD_SELECTION_KIND,
                "eligible_mark_option_ids": [_mark_option_id(mark) for mark in marks],
                "current_observer_unit_instance_ids": list(
                    for_the_greater_good_observer_unit_ids_for_player(
                        context.state,
                        player_id=army.player_id,
                    )
                ),
                "current_spotted_unit_instance_ids": list(
                    for_the_greater_good_spotted_unit_ids_for_player(
                        context.state,
                        player_id=army.player_id,
                    )
                ),
            }
        )
    )
    options = tuple(_mark_decision_option(mark, common_payload) for mark in marks)
    return DecisionRequest(
        request_id=context.state.next_decision_request_id(),
        decision_type=SELECT_FACTION_RULE_SHOOTING_PHASE_START_OPTION_DECISION_TYPE,
        actor_id=army.player_id,
        payload=validate_json_value(common_payload),
        options=(
            *options,
            DecisionOption(
                option_id=FOR_THE_GREATER_GOOD_DONE_OPTION_ID,
                label="No more Observer units",
                payload=validate_json_value(
                    {
                        **common_payload,
                        "submission_kind": FOR_THE_GREATER_GOOD_SELECTION_KIND,
                        "selected_for_the_greater_good_option": "done",
                    }
                ),
            ),
        ),
    )


def apply_for_the_greater_good_result(context: ShootingPhaseStartResultContext) -> bool:
    if type(context) is not ShootingPhaseStartResultContext:
        raise GameLifecycleError("For the Greater Good requires result context.")
    result = context.result
    if result.actor_id is None:
        raise GameLifecycleError("For the Greater Good result requires an actor.")
    player_id = result.actor_id
    army = _tau_empire_army_for_player(context.state, player_id=player_id)
    if army is None:
        raise GameLifecycleError("For the Greater Good actor does not own T'au Empire.")
    if _for_the_greater_good_done_this_shooting_phase(context.state, player_id=player_id):
        raise GameLifecycleError("For the Greater Good was already completed this Shooting phase.")

    payload = _payload_object(result.payload)
    selected = _payload_string(payload, key="selected_for_the_greater_good_option")
    if selected == "done":
        if result.selected_option_id != FOR_THE_GREATER_GOOD_DONE_OPTION_ID:
            raise GameLifecycleError("For the Greater Good done option ID drift.")
        _record_for_the_greater_good_done(context, player_id=player_id)
        return True
    if selected != "mark":
        raise GameLifecycleError("For the Greater Good selection is unsupported.")

    current_marks = {
        _mark_option_id(mark): mark
        for mark in _eligible_for_the_greater_good_marks(context, army=army)
    }
    mark = current_marks.get(result.selected_option_id)
    if mark is None:
        raise GameLifecycleError("For the Greater Good mark is no longer eligible.")
    if mark.observer_rules_unit.unit_instance_id != _payload_string(
        payload, key="observer_rules_unit_instance_id"
    ):
        raise GameLifecycleError("For the Greater Good observer payload drift.")
    if mark.spotted_rules_unit.unit_instance_id != _payload_string(
        payload, key="spotted_unit_instance_id"
    ):
        raise GameLifecycleError("For the Greater Good spotted payload drift.")
    if mark.observer_has_markerlight != _payload_bool(payload, key="observer_has_markerlight"):
        raise GameLifecycleError("For the Greater Good Markerlight payload drift.")

    _record_for_the_greater_good_mark(context, player_id=player_id, mark=mark)
    return True


def for_the_greater_good_spotted_unit_ids_for_player(
    state: GameState,
    *,
    player_id: str,
) -> tuple[str, ...]:
    return tuple(
        sorted(
            _payload_string(_payload_object(effect.effect_payload), key="spotted_unit_instance_id")
            for effect in _active_for_the_greater_good_effects_for_player(
                state,
                player_id=player_id,
            )
        )
    )


def for_the_greater_good_observer_unit_ids_for_player(
    state: GameState,
    *,
    player_id: str,
) -> tuple[str, ...]:
    return tuple(
        sorted(
            _payload_string(
                _payload_object(effect.effect_payload),
                key="observer_rules_unit_instance_id",
            )
            for effect in _active_for_the_greater_good_effects_for_player(
                state,
                player_id=player_id,
            )
        )
    )


def for_the_greater_good_weapon_profile_modifier(
    context: WeaponProfileModifierContext,
) -> WeaponProfile:
    if type(context) is not WeaponProfileModifierContext:
        raise GameLifecycleError("For the Greater Good weapon modifier requires context.")
    profile = context.weapon_profile
    if context.source_phase is not BattlePhase.SHOOTING:
        return profile
    if profile.range_profile.kind is RangeProfileKind.MELEE:
        return profile

    attacking_rules_unit = rules_unit_view_by_id(
        state=context.state,
        unit_instance_id=context.attacking_unit_instance_id,
    )
    target_rules_unit = rules_unit_view_by_id(
        state=context.state,
        unit_instance_id=context.target_unit_instance_id,
    )
    player_id = attacking_rules_unit.owner_player_id
    if not _rules_unit_has_for_the_greater_good(attacking_rules_unit):
        return profile
    if attacking_rules_unit.unit_instance_id in set(
        for_the_greater_good_observer_unit_ids_for_player(context.state, player_id=player_id)
    ):
        return profile

    spotted_effect = _active_for_the_greater_good_effect_for_target(
        context.state,
        player_id=player_id,
        target_rules_unit_instance_id=target_rules_unit.unit_instance_id,
    )
    if spotted_effect is None:
        return profile
    if profile.skill.characteristic is not Characteristic.BALLISTIC_SKILL:
        raise GameLifecycleError("For the Greater Good requires a Ballistic Skill attack.")

    modified = replace(
        profile,
        skill=_improve_ballistic_skill(profile.skill),
        source_ids=_source_ids_with_for_the_greater_good(profile.source_ids),
    )
    effect_payload = _payload_object(spotted_effect.effect_payload)
    if not _payload_bool(effect_payload, key="observer_has_markerlight"):
        return modified
    return replace(
        modified,
        keywords=_weapon_keywords_with_ignores_cover(modified.keywords),
    )


def _eligible_for_the_greater_good_marks(
    context: ShootingPhaseStartRequestContext | ShootingPhaseStartResultContext,
    *,
    army: ArmyDefinition,
) -> tuple[ForTheGreaterGoodMarkOption, ...]:
    observer_ids = set(
        for_the_greater_good_observer_unit_ids_for_player(context.state, player_id=army.player_id)
    )
    spotted_ids = set(
        for_the_greater_good_spotted_unit_ids_for_player(context.state, player_id=army.player_id)
    )
    enemy_target_ids = _placed_enemy_rules_unit_ids(context.state, player_id=army.player_id)
    marks: list[ForTheGreaterGoodMarkOption] = []
    for observer_id in _placed_friendly_rules_unit_ids(context.state, player_id=army.player_id):
        if observer_id in observer_ids:
            continue
        observer_rules_unit = rules_unit_view_by_id(
            state=context.state,
            unit_instance_id=observer_id,
        )
        if not _rules_unit_is_eligible_observer(context, observer_rules_unit):
            continue
        observer_has_markerlight = _rules_unit_has_keyword(
            observer_rules_unit,
            MARKERLIGHT_KEYWORD,
        )
        for target_id in enemy_target_ids:
            if target_id in spotted_ids:
                continue
            target_rules_unit = rules_unit_view_by_id(
                state=context.state,
                unit_instance_id=target_id,
            )
            if not _rules_unit_has_visible_target(
                context.state,
                ruleset_descriptor=context.ruleset_descriptor,
                observer_rules_unit=observer_rules_unit,
                target_rules_unit=target_rules_unit,
            ):
                continue
            marks.append(
                ForTheGreaterGoodMarkOption(
                    observer_rules_unit=observer_rules_unit,
                    spotted_rules_unit=target_rules_unit,
                    observer_has_markerlight=observer_has_markerlight,
                )
            )
    return tuple(
        sorted(
            marks,
            key=lambda mark: (
                mark.observer_rules_unit.unit_instance_id,
                mark.spotted_rules_unit.unit_instance_id,
            ),
        )
    )


def _rules_unit_is_eligible_observer(
    context: ShootingPhaseStartRequestContext | ShootingPhaseStartResultContext,
    rules_unit: RulesUnitView,
) -> bool:
    if not _rules_unit_has_for_the_greater_good(rules_unit):
        return False
    if _rules_unit_has_keyword(rules_unit, FORTIFICATION_KEYWORD):
        return False
    if _rules_unit_is_battle_shocked(context.state, rules_unit):
        return False
    if _rules_unit_was_selected_to_shoot_this_phase(context.state, rules_unit):
        return False
    return shooting_rules_unit_is_eligible_to_shoot(
        state=context.state,
        rules_unit=rules_unit,
        ruleset_descriptor=context.ruleset_descriptor,
        army_catalog=context.army_catalog,
        player_id=rules_unit.owner_player_id,
        shooting_target_restriction_hooks=context.shooting_target_restriction_hooks,
    )


def _mark_decision_option(
    mark: ForTheGreaterGoodMarkOption,
    common_payload: dict[str, JsonValue],
) -> DecisionOption:
    observer_id = mark.observer_rules_unit.unit_instance_id
    target_id = mark.spotted_rules_unit.unit_instance_id
    return DecisionOption(
        option_id=_mark_option_id(mark),
        label=(
            f"{_rules_unit_label(mark.observer_rules_unit)} spots "
            f"{_rules_unit_label(mark.spotted_rules_unit)}"
        ),
        payload=validate_json_value(
            {
                **common_payload,
                "submission_kind": FOR_THE_GREATER_GOOD_SELECTION_KIND,
                "selected_for_the_greater_good_option": "mark",
                "observer_rules_unit_instance_id": observer_id,
                "observer_component_unit_instance_ids": list(
                    mark.observer_rules_unit.component_unit_instance_ids
                ),
                "observer_has_markerlight": mark.observer_has_markerlight,
                "spotted_unit_instance_id": target_id,
                "spotted_owner_player_id": mark.spotted_rules_unit.owner_player_id,
            }
        ),
    )


def _mark_option_id(mark: ForTheGreaterGoodMarkOption) -> str:
    return (
        "tau-empire:for-the-greater-good:observer:"
        f"{mark.observer_rules_unit.unit_instance_id}:spotted:"
        f"{mark.spotted_rules_unit.unit_instance_id}"
    )


def _record_for_the_greater_good_done(
    context: ShootingPhaseStartResultContext,
    *,
    player_id: str,
) -> None:
    done_state = FactionRuleState(
        state_id=(
            f"tau-empire:for-the-greater-good:done:{context.state.game_id}:"
            f"round-{context.state.battle_round:02d}:{player_id}:shooting"
        ),
        player_id=player_id,
        faction_id=TAU_EMPIRE_FACTION_ID,
        source_rule_id=SOURCE_RULE_ID,
        state_kind=FOR_THE_GREATER_GOOD_DONE_STATE_KIND,
        setup_step=SetupStep.DECLARE_BATTLE_FORMATIONS,
        request_id=context.request.request_id,
        result_id=context.result.result_id,
        payload=validate_json_value(
            {
                "game_id": context.state.game_id,
                "battle_round": context.state.battle_round,
                "phase": BattlePhase.SHOOTING.value,
                "active_player_id": player_id,
                "player_id": player_id,
                "selected_for_the_greater_good_option": "done",
                "source_rule_id": SOURCE_RULE_ID,
                "hook_id": HOOK_ID,
            }
        ),
    )
    context.state.record_faction_rule_state(done_state)
    context.decisions.event_log.append(
        "tau_empire_for_the_greater_good_done",
        validate_json_value(
            {
                "game_id": context.state.game_id,
                "battle_round": context.state.battle_round,
                "phase": BattlePhase.SHOOTING.value,
                "player_id": player_id,
                "faction_rule_state": done_state.to_payload(),
                "source_rule_id": SOURCE_RULE_ID,
                "hook_id": HOOK_ID,
                "request_id": context.request.request_id,
                "result_id": context.result.result_id,
            }
        ),
    )


def _record_for_the_greater_good_mark(
    context: ShootingPhaseStartResultContext,
    *,
    player_id: str,
    mark: ForTheGreaterGoodMarkOption,
) -> None:
    effect = _for_the_greater_good_spotted_effect(context, player_id=player_id, mark=mark)
    context.state.record_persisting_effect(effect)
    context.decisions.event_log.append(
        "tau_empire_for_the_greater_good_spotted",
        validate_json_value(
            {
                "game_id": context.state.game_id,
                "battle_round": context.state.battle_round,
                "phase": BattlePhase.SHOOTING.value,
                "player_id": player_id,
                "persisting_effect": effect.to_payload(),
                "source_rule_id": SOURCE_RULE_ID,
                "hook_id": HOOK_ID,
                "request_id": context.request.request_id,
                "result_id": context.result.result_id,
            }
        ),
    )


def _for_the_greater_good_spotted_effect(
    context: ShootingPhaseStartResultContext,
    *,
    player_id: str,
    mark: ForTheGreaterGoodMarkOption,
) -> PersistingEffect:
    observer_id = mark.observer_rules_unit.unit_instance_id
    target_id = mark.spotted_rules_unit.unit_instance_id
    expiration = EffectExpiration.end_phase(
        battle_round=context.state.battle_round,
        phase=BattlePhaseKind.SHOOTING,
        player_id=player_id,
    )
    return PersistingEffect(
        effect_id=(
            f"tau-empire:for-the-greater-good:spotted:{context.state.game_id}:"
            f"round-{context.state.battle_round:02d}:{player_id}:{observer_id}:{target_id}"
        ),
        source_rule_id=SOURCE_RULE_ID,
        owner_player_id=player_id,
        target_unit_instance_ids=(observer_id, target_id),
        started_battle_round=context.state.battle_round,
        started_phase=BattlePhaseKind.SHOOTING,
        expiration=expiration,
        effect_payload=validate_json_value(
            {
                "game_id": context.state.game_id,
                "battle_round": context.state.battle_round,
                "phase": BattlePhase.SHOOTING.value,
                "active_player_id": player_id,
                "player_id": player_id,
                "effect_kind": FOR_THE_GREATER_GOOD_EFFECT_KIND,
                "observer_rules_unit_instance_id": observer_id,
                "observer_component_unit_instance_ids": list(
                    mark.observer_rules_unit.component_unit_instance_ids
                ),
                "observer_has_markerlight": mark.observer_has_markerlight,
                "spotted_unit_instance_id": target_id,
                "spotted_owner_player_id": mark.spotted_rules_unit.owner_player_id,
                "source_rule_id": SOURCE_RULE_ID,
                "hook_id": HOOK_ID,
                "selected_option_id": context.result.selected_option_id,
                "request_id": context.request.request_id,
                "result_id": context.result.result_id,
            }
        ),
    )


def _for_the_greater_good_done_this_shooting_phase(
    state: GameState,
    *,
    player_id: str,
) -> bool:
    requested_player_id = _validate_identifier("player_id", player_id)
    matching = tuple(
        stored
        for stored in state.faction_rule_states_for_player(
            player_id=requested_player_id,
            state_kind=FOR_THE_GREATER_GOOD_DONE_STATE_KIND,
        )
        if _done_state_matches_current_shooting_phase(state, stored)
    )
    if len(matching) > 1:
        raise GameLifecycleError("For the Greater Good found multiple done states.")
    return bool(matching)


def _done_state_matches_current_shooting_phase(
    state: GameState,
    stored: FactionRuleState,
) -> bool:
    payload = _payload_object(stored.payload)
    return (
        stored.source_rule_id == SOURCE_RULE_ID
        and payload.get("battle_round") == state.battle_round
        and payload.get("phase") == BattlePhase.SHOOTING.value
        and payload.get("selected_for_the_greater_good_option") == "done"
    )


def _active_for_the_greater_good_effect_for_target(
    state: GameState,
    *,
    player_id: str,
    target_rules_unit_instance_id: str,
) -> PersistingEffect | None:
    requested_target_id = _validate_identifier(
        "target_rules_unit_instance_id",
        target_rules_unit_instance_id,
    )
    effects = tuple(
        effect
        for effect in _active_for_the_greater_good_effects_for_player(state, player_id=player_id)
        if _payload_string(_payload_object(effect.effect_payload), key="spotted_unit_instance_id")
        == requested_target_id
    )
    if len(effects) > 1:
        raise GameLifecycleError("For the Greater Good found multiple Spotted effects.")
    if not effects:
        return None
    return effects[0]


def _active_for_the_greater_good_effects_for_player(
    state: GameState,
    *,
    player_id: str,
) -> tuple[PersistingEffect, ...]:
    requested_player_id = _validate_identifier("player_id", player_id)
    effects: list[PersistingEffect] = []
    for effect in state.persisting_effects:
        if effect.source_rule_id != SOURCE_RULE_ID:
            continue
        if effect.owner_player_id != requested_player_id:
            continue
        payload = _payload_object(effect.effect_payload)
        if payload.get("effect_kind") != FOR_THE_GREATER_GOOD_EFFECT_KIND:
            continue
        if payload.get("battle_round") != state.battle_round:
            continue
        if payload.get("phase") != BattlePhase.SHOOTING.value:
            continue
        effects.append(effect)
    return tuple(sorted(effects, key=lambda effect: effect.effect_id))


def _rules_unit_has_visible_target(
    state: GameState,
    *,
    ruleset_descriptor: RulesetDescriptor,
    observer_rules_unit: RulesUnitView,
    target_rules_unit: RulesUnitView,
) -> bool:
    scenario = _battlefield_scenario(state)
    terrain_features = _terrain_features_for_state(state)
    for component in observer_rules_unit.components:
        if unit_has_line_of_sight_to_target(
            scenario=scenario,
            ruleset_descriptor=ruleset_descriptor,
            observing_unit=component.unit,
            target_unit_id=target_rules_unit.unit_instance_id,
            terrain_features=terrain_features,
        ):
            return True
    return False


def _battlefield_scenario(state: GameState) -> BattlefieldScenario:
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("For the Greater Good requires battlefield_state.")
    try:
        scenario = BattlefieldScenario(
            armies=tuple(state.army_definitions),
            battlefield_state=battlefield_state,
        )
        scenario.assert_all_mustered_models_placed_or_accounted(state.unavailable_model_ids())
    except PlacementError as exc:
        raise GameLifecycleError("For the Greater Good battlefield scenario is invalid.") from exc
    return scenario


def _terrain_features_for_state(state: GameState) -> tuple[TerrainFeatureDefinition, ...]:
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("For the Greater Good requires battlefield_state.")
    return battlefield_state.terrain_features


def _placed_friendly_rules_unit_ids(state: GameState, *, player_id: str) -> tuple[str, ...]:
    return _placed_rules_unit_ids(state, player_id=player_id, include_enemies=False)


def _placed_enemy_rules_unit_ids(state: GameState, *, player_id: str) -> tuple[str, ...]:
    return _placed_rules_unit_ids(state, player_id=player_id, include_enemies=True)


def _placed_rules_unit_ids(
    state: GameState,
    *,
    player_id: str,
    include_enemies: bool,
) -> tuple[str, ...]:
    requested_player_id = _validate_identifier("player_id", player_id)
    if type(include_enemies) is not bool:
        raise GameLifecycleError("For the Greater Good include_enemies must be bool.")
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("For the Greater Good requires battlefield_state.")
    unit_ids: list[str] = []
    seen: set[str] = set()
    armies = tuple(state.army_definitions)
    for placed_army in battlefield_state.placed_armies:
        is_enemy = placed_army.player_id != requested_player_id
        if is_enemy != include_enemies:
            continue
        for placement in placed_army.unit_placements:
            rules_unit_id = rules_unit_id_for_unit_id(
                armies=armies,
                unit_instance_id=placement.unit_instance_id,
            )
            if rules_unit_id in seen:
                continue
            seen.add(rules_unit_id)
            unit_ids.append(rules_unit_id)
    return tuple(sorted(unit_ids))


def _rules_unit_was_selected_to_shoot_this_phase(
    state: GameState,
    rules_unit: RulesUnitView,
) -> bool:
    shooting_state = state.shooting_phase_state
    if shooting_state is None:
        return False
    unit_ids = {rules_unit.unit_instance_id, *rules_unit.component_unit_instance_ids}
    selected_ids = {
        *shooting_state.selected_unit_ids,
        *shooting_state.shot_unit_ids,
        *shooting_state.skipped_unit_ids,
    }
    if shooting_state.active_selection is not None:
        selected_ids.add(shooting_state.active_selection.unit_instance_id)
    return bool(unit_ids & selected_ids)


def _rules_unit_is_battle_shocked(state: GameState, rules_unit: RulesUnitView) -> bool:
    if type(rules_unit) is not RulesUnitView:
        raise GameLifecycleError("For the Greater Good Battle-shock check requires rules unit.")
    shocked_ids = set(state.battle_shocked_unit_ids)
    return bool(
        shocked_ids & {rules_unit.unit_instance_id, *rules_unit.component_unit_instance_ids}
    )


def _rules_unit_has_for_the_greater_good(rules_unit: RulesUnitView) -> bool:
    if type(rules_unit) is not RulesUnitView:
        raise GameLifecycleError("For the Greater Good ability check requires rules unit.")
    return any(
        _unit_has_for_the_greater_good(component.unit) for component in rules_unit.components
    )


def _unit_has_for_the_greater_good(unit: UnitInstance) -> bool:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("For the Greater Good ability check requires UnitInstance.")
    return _unit_has_named_ability(unit, FOR_THE_GREATER_GOOD_ABILITY_NAME) or _unit_has_keyword(
        unit.faction_keywords,
        TAU_EMPIRE_FACTION_KEYWORD,
    )


def _unit_has_named_ability(unit: UnitInstance, ability_name: str) -> bool:
    requested_name = _normalise_rule_token(_validate_identifier("ability_name", ability_name))
    return any(
        _normalise_rule_token(ability.name) == requested_name
        for ability in unit.datasheet_abilities
    )


def _rules_unit_has_keyword(rules_unit: RulesUnitView, keyword: str) -> bool:
    if type(rules_unit) is not RulesUnitView:
        raise GameLifecycleError("For the Greater Good keyword check requires rules unit.")
    return _unit_has_keyword((*rules_unit.keywords, *rules_unit.faction_keywords), keyword)


def _unit_has_keyword(keywords: tuple[str, ...], keyword: str) -> bool:
    if type(keywords) is not tuple:
        raise GameLifecycleError("For the Greater Good keyword list must be a tuple.")
    requested = _normalise_rule_token(_validate_identifier("keyword", keyword))
    return any(_normalise_rule_token(stored) == requested for stored in keywords)


def _tau_empire_army_for_player(
    state: GameState,
    *,
    player_id: str,
) -> ArmyDefinition | None:
    requested_player_id = _validate_identifier("player_id", player_id)
    matching = tuple(
        army
        for army in state.army_definitions
        if army.player_id == requested_player_id
        and army.detachment_selection.faction_id == TAU_EMPIRE_FACTION_ID
    )
    if len(matching) > 1:
        raise GameLifecycleError("For the Greater Good found multiple T'au Empire armies.")
    if not matching:
        return None
    return matching[0]


def _improve_ballistic_skill(skill: CharacteristicValue) -> CharacteristicValue:
    if type(skill) is not CharacteristicValue:
        raise GameLifecycleError("For the Greater Good ballistic skill requires value.")
    if skill.characteristic is not Characteristic.BALLISTIC_SKILL:
        raise GameLifecycleError("For the Greater Good ballistic skill characteristic drift.")
    if not skill.is_numeric:
        raise GameLifecycleError("For the Greater Good cannot improve non-numeric Ballistic Skill.")
    return CharacteristicValue.from_raw(
        Characteristic.BALLISTIC_SKILL,
        _improve_skill(skill.final),
    )


def _improve_skill(current: int) -> int:
    _validate_non_negative_int("skill", current)
    if current <= 2:
        return current
    return current - 1


def _weapon_keywords_with_ignores_cover(
    keywords: tuple[WeaponKeyword, ...],
) -> tuple[WeaponKeyword, ...]:
    if type(keywords) is not tuple:
        raise GameLifecycleError("For the Greater Good keywords must be a tuple.")
    if WeaponKeyword.IGNORES_COVER in keywords:
        return keywords
    return (*keywords, WeaponKeyword.IGNORES_COVER)


def _source_ids_with_for_the_greater_good(source_ids: tuple[str, ...]) -> tuple[str, ...]:
    if type(source_ids) is not tuple:
        raise GameLifecycleError("For the Greater Good source_ids must be a tuple.")
    return tuple(sorted({*source_ids, SOURCE_RULE_ID}))


def _rules_unit_label(rules_unit: RulesUnitView) -> str:
    if type(rules_unit) is not RulesUnitView:
        raise GameLifecycleError("For the Greater Good label requires rules unit.")
    if len(rules_unit.components) == 1:
        return rules_unit.components[0].unit.name
    return " / ".join(component.unit.name for component in rules_unit.components)


def _active_player_id(state: GameState) -> str:
    if state.active_player_id is None:
        raise GameLifecycleError("For the Greater Good requires active_player_id.")
    return state.active_player_id


def _payload_object(payload: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(payload, dict):
        raise GameLifecycleError("For the Greater Good payload must be an object.")
    return payload


def _payload_string(payload: dict[str, JsonValue], *, key: str) -> str:
    value = payload.get(key)
    if type(value) is not str:
        raise GameLifecycleError(f"For the Greater Good payload field {key} must be a string.")
    return value


def _payload_bool(payload: dict[str, JsonValue], *, key: str) -> bool:
    value = payload.get(key)
    if type(value) is not bool:
        raise GameLifecycleError(f"For the Greater Good payload field {key} must be a bool.")
    return value


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"For the Greater Good {field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"For the Greater Good {field_name} must not be empty.")
    return stripped


def _validate_non_negative_int(field_name: str, value: object) -> int:
    if type(value) is not int or value < 0:
        raise GameLifecycleError(f"For the Greater Good {field_name} must be non-negative int.")
    return value


def _normalise_rule_token(value: str) -> str:
    if type(value) is not str:
        raise GameLifecycleError("For the Greater Good token must be a string.")
    return "".join(character for character in value.upper() if character.isalnum())
