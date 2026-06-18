from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from itertools import combinations
from typing import TYPE_CHECKING

from warhammer40k_core.core.dice import DiceExpression, DiceRollSpec
from warhammer40k_core.core.modifiers import RollModifier
from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind
from warhammer40k_core.core.weapon_profiles import (
    AbilityDescriptor,
    RangeProfileKind,
    WeaponKeyword,
    WeaponProfile,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.battle_round_hooks import (
    SELECT_FACTION_RULE_BATTLE_ROUND_OPTION_DECISION_TYPE,
    BattleRoundStartHookBinding,
    BattleRoundStartRequestContext,
    BattleRoundStartResultContext,
)
from warhammer40k_core.engine.damage_allocation import (
    DestructionReactionKind,
    DestructionReactionSource,
)
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import EventLog, JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentContribution
from warhammer40k_core.engine.fight_activation_abilities import (
    FIGHT_ACTIVATION_MOVEMENT_DISTANCE_EFFECT_KIND,
    FightActivationAbilityContext,
    FightActivationAbilityHookBinding,
    FightActivationAbilityOption,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.runtime_modifiers import (
    ChargeRollModifierBinding,
    ChargeRollModifierContext,
    WeaponProfileModifierBinding,
    WeaponProfileModifierContext,
)
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitInstance

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


CONTRIBUTION_ID = "warhammer_40000_11th:world_eaters:army_rule:scaffold"
HOOK_ID = "warhammer_40000_11th:world_eaters:army_rule:blessings_of_khorne"
RAGE_FUELLED_INVIGORATION_HOOK_ID = f"{HOOK_ID}:rage_fuelled_invigoration"
TOTAL_CARNAGE_HOOK_ID = f"{HOOK_ID}:total_carnage"
SOURCE_RULE_ID = "phase17f:phase17e:world-eaters:army-rule"
WORLD_EATERS_FACTION_ID = "world-eaters"
WORLD_EATERS_FACTION_KEYWORD = "WORLD EATERS"
BLESSINGS_OF_KHORNE_EFFECT_KIND = "world_eaters_blessings_of_khorne"
BLESSINGS_OF_KHORNE_ABILITY_ID = "blessings_of_khorne"
ICON_OF_KHORNE_RULE_UPDATE_SOURCE = (
    "warhammer_40000_11th:world_eaters:faction_pack:rules_updates:icon_of_khorne"
)
UNBRIDLED_BLOODLUST_RULE_UPDATE_SOURCE = (
    "warhammer_40000_11th:world_eaters:faction_pack:rules_updates:unbridled_bloodlust"
)
BLESSINGS_DICE_COUNT = 8
MAX_BLESSINGS_PER_ROLL = 2
TOTAL_CARNAGE_TRIGGER_THRESHOLD = 4
UNBRIDLED_BLOODLUST_CHARGE_MODIFIER_ID = f"{HOOK_ID}:unbridled_bloodlust:charge_roll"


class BlessingOfKhorne(StrEnum):
    UNBRIDLED_BLOODLUST = "unbridled_bloodlust"
    RAGE_FUELLED_INVIGORATION = "rage_fuelled_invigoration"
    TOTAL_CARNAGE = "total_carnage"
    MARTIAL_EXCELLENCE = "martial_excellence"
    WARP_BLADES = "warp_blades"
    DECAPITATING_STRIKES = "decapitating_strikes"


@dataclass(frozen=True, slots=True)
class DiceRecipe:
    count: int
    min_value: int

    def __post_init__(self) -> None:
        if type(self.count) is not int or self.count < 1:
            raise GameLifecycleError("Blessings of Khorne dice recipe count must be positive.")
        if type(self.min_value) is not int or not 1 <= self.min_value <= 6:
            raise GameLifecycleError("Blessings of Khorne dice recipe min_value must be 1-6.")


@dataclass(frozen=True, slots=True)
class BlessingDefinition:
    blessing: BlessingOfKhorne
    label: str
    recipes: tuple[DiceRecipe, ...]
    effect_summary: str

    def __post_init__(self) -> None:
        if type(self.blessing) is not BlessingOfKhorne:
            raise GameLifecycleError("Blessings of Khorne definition blessing drift.")
        if type(self.label) is not str or not self.label.strip():
            raise GameLifecycleError("Blessings of Khorne definition label must be non-empty.")
        if type(self.recipes) is not tuple or not self.recipes:
            raise GameLifecycleError("Blessings of Khorne definition requires recipes.")
        for recipe in self.recipes:
            if type(recipe) is not DiceRecipe:
                raise GameLifecycleError("Blessings of Khorne recipes must be DiceRecipe.")
        if type(self.effect_summary) is not str or not self.effect_summary.strip():
            raise GameLifecycleError("Blessings of Khorne effect summary must be non-empty.")


BLESSING_DEFINITIONS: tuple[BlessingDefinition, ...] = (
    BlessingDefinition(
        blessing=BlessingOfKhorne.UNBRIDLED_BLOODLUST,
        label="Unbridled Bloodlust",
        recipes=(DiceRecipe(count=2, min_value=1),),
        effect_summary="This unit has +1 to charge rolls.",
    ),
    BlessingDefinition(
        blessing=BlessingOfKhorne.RAGE_FUELLED_INVIGORATION,
        label="Rage-fuelled Invigoration",
        recipes=(DiceRecipe(count=2, min_value=2),),
        effect_summary='Pile-in and Consolidation moves can be up to 6".',
    ),
    BlessingDefinition(
        blessing=BlessingOfKhorne.TOTAL_CARNAGE,
        label="Total Carnage",
        recipes=(DiceRecipe(count=2, min_value=3),),
        effect_summary="Destroyed-by-melee models can fight on death on a 4+.",
    ),
    BlessingDefinition(
        blessing=BlessingOfKhorne.MARTIAL_EXCELLENCE,
        label="Martial Excellence",
        recipes=(DiceRecipe(count=2, min_value=4), DiceRecipe(count=3, min_value=1)),
        effect_summary="Melee weapons have Sustained Hits 1.",
    ),
    BlessingDefinition(
        blessing=BlessingOfKhorne.WARP_BLADES,
        label="Warp Blades",
        recipes=(DiceRecipe(count=2, min_value=5), DiceRecipe(count=3, min_value=2)),
        effect_summary="Melee weapons have Lethal Hits.",
    ),
    BlessingDefinition(
        blessing=BlessingOfKhorne.DECAPITATING_STRIKES,
        label="Decapitating Strikes",
        recipes=(DiceRecipe(count=2, min_value=6), DiceRecipe(count=3, min_value=3)),
        effect_summary="Melee attacks that target Infantry have Devastating Wounds.",
    ),
)
_DEFINITIONS_BY_BLESSING = {definition.blessing: definition for definition in BLESSING_DEFINITIONS}


def runtime_contribution() -> RuntimeContentContribution:
    return RuntimeContentContribution(
        contribution_id=CONTRIBUTION_ID,
        battle_round_start_hook_bindings=(
            BattleRoundStartHookBinding(
                hook_id=HOOK_ID,
                source_id=SOURCE_RULE_ID,
                request_handler=blessings_selection_request,
                result_handler=apply_blessings_selection_result,
            ),
        ),
        charge_roll_modifier_bindings=(
            ChargeRollModifierBinding(
                modifier_id=UNBRIDLED_BLOODLUST_CHARGE_MODIFIER_ID,
                source_id=SOURCE_RULE_ID,
                handler=unbridled_bloodlust_charge_roll_modifier,
            ),
        ),
        fight_activation_ability_hook_bindings=(
            FightActivationAbilityHookBinding(
                hook_id=RAGE_FUELLED_INVIGORATION_HOOK_ID,
                source_id=SOURCE_RULE_ID,
                handler=rage_fuelled_invigoration_option,
            ),
        ),
        weapon_profile_modifier_bindings=(
            WeaponProfileModifierBinding(
                modifier_id=f"{HOOK_ID}:weapon-profile-keywords",
                source_id=SOURCE_RULE_ID,
                handler=blessings_weapon_profile_modifier,
            ),
        ),
    )


def blessings_selection_request(
    context: BattleRoundStartRequestContext,
) -> DecisionRequest | None:
    if type(context) is not BattleRoundStartRequestContext:
        raise GameLifecycleError("Blessings of Khorne requires request context.")
    for army in _world_eaters_armies(context.state):
        if _blessings_selection_recorded_for_player(context.state, player_id=army.player_id):
            continue
        target_unit_ids = _eligible_blessings_unit_ids_for_army(army)
        if not target_unit_ids:
            continue
        bloodshed_points = bloodshed_points_available(
            context.state,
            event_log=context.decisions.event_log,
            player_id=army.player_id,
        )
        dice_count = BLESSINGS_DICE_COUNT + bloodshed_points
        roll_state = DiceRollManager(
            context.state.game_id,
            event_log=context.decisions.event_log,
        ).roll(
            DiceRollSpec(
                expression=DiceExpression(quantity=dice_count, sides=6),
                reason="Blessings of Khorne roll",
                roll_type="world_eaters_blessings_of_khorne",
                actor_id=army.player_id,
            )
        )
        dice_values = tuple(roll_state.current_values)
        return DecisionRequest(
            request_id=context.state.next_decision_request_id(),
            decision_type=SELECT_FACTION_RULE_BATTLE_ROUND_OPTION_DECISION_TYPE,
            actor_id=army.player_id,
            payload=validate_json_value(
                {
                    "game_id": context.state.game_id,
                    "battle_round": context.state.battle_round,
                    "phase": BattlePhase.COMMAND.value,
                    "faction_id": WORLD_EATERS_FACTION_ID,
                    "source_rule_id": SOURCE_RULE_ID,
                    "hook_id": HOOK_ID,
                    "effect_kind": BLESSINGS_OF_KHORNE_EFFECT_KIND,
                    "roll_state": roll_state.to_payload(),
                    "dice_values": list(dice_values),
                    "base_dice_count": BLESSINGS_DICE_COUNT,
                    "bloodshed_points_spent": bloodshed_points,
                    "target_unit_instance_ids": list(target_unit_ids),
                    "rules_update_sources": (
                        [UNBRIDLED_BLOODLUST_RULE_UPDATE_SOURCE]
                        if bloodshed_points == 0
                        else [
                            UNBRIDLED_BLOODLUST_RULE_UPDATE_SOURCE,
                            ICON_OF_KHORNE_RULE_UPDATE_SOURCE,
                        ]
                    ),
                }
            ),
            options=blessings_selection_options(
                player_id=army.player_id,
                battle_round=context.state.battle_round,
                dice_values=dice_values,
                bloodshed_points=bloodshed_points,
            ),
        )
    return None


def apply_blessings_selection_result(context: BattleRoundStartResultContext) -> bool:
    if type(context) is not BattleRoundStartResultContext:
        raise GameLifecycleError("Blessings of Khorne requires result context.")
    if context.request.decision_type != SELECT_FACTION_RULE_BATTLE_ROUND_OPTION_DECISION_TYPE:
        return False
    request_payload = _payload_object(context.request.payload)
    if request_payload.get("hook_id") != HOOK_ID:
        return False
    result = context.result
    if result.actor_id is None:
        raise GameLifecycleError("Blessings of Khorne selection requires an actor.")
    player_id = result.actor_id
    army = _world_eaters_army_for_player(context.state, player_id=player_id)
    if army is None:
        raise GameLifecycleError("Blessings of Khorne actor does not own World Eaters.")
    if _blessings_selection_recorded_for_player(context.state, player_id=player_id):
        raise GameLifecycleError("Blessings of Khorne is already recorded for this round.")
    payload = _payload_object(result.payload)
    blessings = tuple(
        _blessing_from_token(token)
        for token in _payload_string_list(payload, key="selected_blessing_ids")
    )
    target_unit_ids = _eligible_blessings_unit_ids_for_army(army)
    if not target_unit_ids:
        raise GameLifecycleError("Blessings of Khorne selection has no eligible units.")
    effect = PersistingEffect(
        effect_id=(
            f"{HOOK_ID}:{player_id}:round-{context.state.battle_round:02d}:active-blessings"
        ),
        source_rule_id=SOURCE_RULE_ID,
        owner_player_id=player_id,
        target_unit_instance_ids=target_unit_ids,
        started_battle_round=context.state.battle_round,
        started_phase=BattlePhaseKind.COMMAND,
        expiration=EffectExpiration.end_battle_round(battle_round=context.state.battle_round),
        effect_payload=validate_json_value(
            {
                "effect_kind": BLESSINGS_OF_KHORNE_EFFECT_KIND,
                "battle_round": context.state.battle_round,
                "phase": BattlePhase.COMMAND.value,
                "player_id": player_id,
                "faction_id": WORLD_EATERS_FACTION_ID,
                "source_rule_id": SOURCE_RULE_ID,
                "hook_id": HOOK_ID,
                "selected_blessing_ids": [blessing.value for blessing in blessings],
                "selected_blessing_labels": [_DEFINITIONS_BY_BLESSING[b].label for b in blessings],
                "selected_option_id": result.selected_option_id,
                "request_id": context.request.request_id,
                "result_id": result.result_id,
                "dice_values": _payload_int_list(payload, key="dice_values"),
                "consumed_dice_by_blessing_id": _payload_index_mapping(
                    payload,
                    key="consumed_dice_by_blessing_id",
                ),
                "bloodshed_points_spent": _payload_non_negative_int(
                    payload,
                    key="bloodshed_points_spent",
                ),
                "rules_update_sources": _payload_string_list(
                    payload,
                    key="rules_update_sources",
                ),
            }
        ),
    )
    context.state.record_persisting_effect(effect)
    if BlessingOfKhorne.TOTAL_CARNAGE in blessings:
        _record_total_carnage_sources(state=context.state, army=army)
    context.decisions.event_log.append(
        "world_eaters_blessings_of_khorne_selected",
        {
            "game_id": context.state.game_id,
            "battle_round": context.state.battle_round,
            "phase": BattlePhase.COMMAND.value,
            "player_id": player_id,
            "source_rule_id": SOURCE_RULE_ID,
            "hook_id": HOOK_ID,
            "selected_blessing_ids": [blessing.value for blessing in blessings],
            "bloodshed_points_spent": _payload_non_negative_int(
                payload,
                key="bloodshed_points_spent",
            ),
            "persisting_effect": effect.to_payload(),
        },
    )
    return True


def blessings_selection_options(
    *,
    player_id: str,
    battle_round: int,
    dice_values: tuple[int, ...],
    bloodshed_points: int,
) -> tuple[DecisionOption, ...]:
    _validate_identifier("player_id", player_id)
    if type(battle_round) is not int or battle_round <= 0:
        raise GameLifecycleError("Blessings of Khorne options require positive battle_round.")
    values = _validate_dice_values(dice_values)
    if type(bloodshed_points) is not int or bloodshed_points < 0:
        raise GameLifecycleError("Blessings of Khorne bloodshed_points must be non-negative.")
    options = [
        _blessing_option(
            player_id=player_id,
            battle_round=battle_round,
            dice_values=values,
            selected=(),
            consumed={},
            bloodshed_points=bloodshed_points,
        )
    ]
    single_allocations: dict[BlessingOfKhorne, tuple[int, ...]] = {}
    for definition in BLESSING_DEFINITIONS:
        allocation = _first_matching_allocation(values, definition.blessing, used_indices=())
        if allocation is None:
            continue
        single_allocations[definition.blessing] = allocation
        options.append(
            _blessing_option(
                player_id=player_id,
                battle_round=battle_round,
                dice_values=values,
                selected=(definition.blessing,),
                consumed={definition.blessing: allocation},
                bloodshed_points=bloodshed_points,
            )
        )
    for first, second in combinations(tuple(BlessingOfKhorne), 2):
        pair_consumed = _first_disjoint_pair_allocation(values, first=first, second=second)
        if pair_consumed is None:
            continue
        options.append(
            _blessing_option(
                player_id=player_id,
                battle_round=battle_round,
                dice_values=values,
                selected=(first, second),
                consumed=pair_consumed,
                bloodshed_points=bloodshed_points,
            )
        )
    return tuple(options)


def active_blessings_for_player(
    state: GameState,
    *,
    player_id: str,
) -> tuple[BlessingOfKhorne, ...]:
    _validate_game_state(state)
    requested_player_id = _validate_identifier("player_id", player_id)
    matching = _active_blessings_effects_for_player(state, player_id=requested_player_id)
    if not matching:
        return ()
    payload = _payload_object(matching[0].effect_payload)
    return tuple(
        _blessing_from_token(token)
        for token in _payload_string_list(payload, key="selected_blessing_ids")
    )


def _blessings_selection_recorded_for_player(
    state: GameState,
    *,
    player_id: str,
) -> bool:
    _validate_game_state(state)
    return bool(_active_blessings_effects_for_player(state, player_id=player_id))


def _active_blessings_effects_for_player(
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
        if payload.get("effect_kind") != BLESSINGS_OF_KHORNE_EFFECT_KIND:
            continue
        if payload.get("battle_round") != state.battle_round:
            continue
        matching.append(effect)
    if len(matching) > 1:
        raise GameLifecycleError("Blessings of Khorne lookup found multiple active effects.")
    return tuple(matching)


def unit_has_active_blessing(
    state: GameState,
    *,
    unit_instance_id: str,
    blessing: BlessingOfKhorne,
) -> bool:
    _validate_game_state(state)
    requested_blessing = _blessing_from_token(blessing)
    unit, army = _unit_and_army_by_id(state, unit_instance_id=unit_instance_id)
    if not _unit_has_blessings_of_khorne(unit):
        return False
    return requested_blessing in active_blessings_for_player(state, player_id=army.player_id)


def unbridled_bloodlust_charge_roll_modifier(
    context: ChargeRollModifierContext,
) -> tuple[RollModifier, ...]:
    if type(context) is not ChargeRollModifierContext:
        raise GameLifecycleError("Unbridled Bloodlust charge modifier requires context.")
    if not unit_has_active_blessing(
        context.state,
        unit_instance_id=context.unit_instance_id,
        blessing=BlessingOfKhorne.UNBRIDLED_BLOODLUST,
    ):
        return context.current_roll_modifiers
    modifier_id = f"{UNBRIDLED_BLOODLUST_CHARGE_MODIFIER_ID}:{context.unit_instance_id}"
    if any(modifier.modifier_id == modifier_id for modifier in context.current_roll_modifiers):
        return context.current_roll_modifiers
    return (
        *context.current_roll_modifiers,
        RollModifier(
            modifier_id=modifier_id,
            source_id=SOURCE_RULE_ID,
            operand=1,
        ),
    )


def rage_fuelled_invigoration_option(
    context: FightActivationAbilityContext,
) -> FightActivationAbilityOption | None:
    if type(context) is not FightActivationAbilityContext:
        raise GameLifecycleError("Rage-fuelled Invigoration requires fight activation context.")
    if not unit_has_active_blessing(
        context.state,
        unit_instance_id=context.unit_instance_id,
        blessing=BlessingOfKhorne.RAGE_FUELLED_INVIGORATION,
    ):
        return None
    return FightActivationAbilityOption(
        hook_id=RAGE_FUELLED_INVIGORATION_HOOK_ID,
        source_id=SOURCE_RULE_ID,
        ability_id=BlessingOfKhorne.RAGE_FUELLED_INVIGORATION.value,
        enhancement_id=BLESSINGS_OF_KHORNE_ABILITY_ID,
        effect_kind=FIGHT_ACTIVATION_MOVEMENT_DISTANCE_EFFECT_KIND,
        pile_in_distance_inches=6.0,
        consolidate_distance_inches=6.0,
        replay_payload={
            "effect_kind": BLESSINGS_OF_KHORNE_EFFECT_KIND,
            "blessing_id": BlessingOfKhorne.RAGE_FUELLED_INVIGORATION.value,
            "unit_instance_id": context.unit_instance_id,
            "pile_in_distance_inches": 6.0,
            "consolidate_distance_inches": 6.0,
        },
        decision_effect_payload={
            "effect_kind": BLESSINGS_OF_KHORNE_EFFECT_KIND,
            "blessing_id": BlessingOfKhorne.RAGE_FUELLED_INVIGORATION.value,
            "source_rule_id": SOURCE_RULE_ID,
        },
    )


def blessings_weapon_profile_modifier(
    context: WeaponProfileModifierContext,
) -> WeaponProfile:
    if type(context) is not WeaponProfileModifierContext:
        raise GameLifecycleError("Blessings weapon profile modifier requires context.")
    if context.source_phase is not BattlePhase.FIGHT:
        return context.weapon_profile
    if context.weapon_profile.range_profile.kind is not RangeProfileKind.MELEE:
        return context.weapon_profile
    blessings = set(
        active_blessings_for_unit(
            context.state,
            unit_instance_id=context.attacking_unit_instance_id,
        )
    )
    if not blessings:
        return context.weapon_profile
    profile = context.weapon_profile
    if BlessingOfKhorne.MARTIAL_EXCELLENCE in blessings:
        profile = _profile_with_keyword_and_ability(
            profile,
            keyword=WeaponKeyword.SUSTAINED_HITS,
            ability=AbilityDescriptor.sustained_hits(1),
        )
    if BlessingOfKhorne.WARP_BLADES in blessings:
        profile = _profile_with_keyword_and_ability(
            profile,
            keyword=WeaponKeyword.LETHAL_HITS,
            ability=AbilityDescriptor.lethal_hits(),
        )
    if BlessingOfKhorne.DECAPITATING_STRIKES in blessings and _target_unit_has_keyword(
        context.state,
        unit_instance_id=context.target_unit_instance_id,
        keyword="INFANTRY",
    ):
        profile = _profile_with_keyword_and_ability(
            profile,
            keyword=WeaponKeyword.DEVASTATING_WOUNDS,
            ability=AbilityDescriptor.devastating_wounds(),
        )
    return profile


def active_blessings_for_unit(
    state: GameState,
    *,
    unit_instance_id: str,
) -> tuple[BlessingOfKhorne, ...]:
    unit, army = _unit_and_army_by_id(state, unit_instance_id=unit_instance_id)
    if not _unit_has_blessings_of_khorne(unit):
        return ()
    return active_blessings_for_player(state, player_id=army.player_id)


def bloodshed_points_available(
    state: GameState,
    *,
    event_log: EventLog,
    player_id: str,
) -> int:
    _validate_game_state(state)
    if type(event_log) is not EventLog:
        raise GameLifecycleError("Bloodshed point calculation requires EventLog.")
    requested_player_id = _validate_identifier("player_id", player_id)
    if _world_eaters_army_for_player(state, player_id=requested_player_id) is None:
        return 0
    if state.battlefield_state is None:
        return 0
    start_index = _last_blessings_selection_event_index(
        state,
        event_log=event_log,
        player_id=requested_player_id,
    )
    interval_events = _model_destroyed_events_after_index(
        state,
        event_log=event_log,
        start_index=start_index,
    )
    completion_events = _unit_destruction_completion_events(
        state,
        interval_events=interval_events,
    )
    points = 0
    for completion in completion_events:
        payload = completion.payload
        if _payload_string(payload, key="destroying_player_id") != requested_player_id:
            continue
        attacking_unit_id = _payload_string(payload, key="attacking_unit_instance_id")
        target_unit_id = _payload_string(payload, key="target_unit_instance_id")
        if _unit_owner_player_id(state, unit_instance_id=target_unit_id) == requested_player_id:
            continue
        attacking_unit, _army = _unit_and_army_by_id(state, unit_instance_id=attacking_unit_id)
        if _unit_contains_icon_of_khorne_at_event(
            state=state,
            unit=attacking_unit,
            completion_event_order=completion.event_order,
            interval_events=interval_events,
        ):
            points += 1
    return points


def _record_total_carnage_sources(*, state: GameState, army: ArmyDefinition) -> None:
    for unit in army.units:
        if not _unit_has_blessings_of_khorne(unit):
            continue
        for model in unit.alive_own_models():
            existing = tuple(
                source
                for source in state.destruction_reaction_sources_for_model(
                    model_instance_id=model.model_instance_id,
                )
                if not source.source_id.startswith(TOTAL_CARNAGE_HOOK_ID)
            )
            source = DestructionReactionSource(
                source_id=(
                    f"{TOTAL_CARNAGE_HOOK_ID}:{army.player_id}:"
                    f"round-{state.battle_round:02d}:{model.model_instance_id}"
                ),
                reaction_kind=DestructionReactionKind.FIGHT_ON_DEATH,
                source_rule_id=SOURCE_RULE_ID,
                optional=True,
                payload={
                    "effect_kind": BLESSINGS_OF_KHORNE_EFFECT_KIND,
                    "blessing_id": BlessingOfKhorne.TOTAL_CARNAGE.value,
                    "trigger_roll_threshold": TOTAL_CARNAGE_TRIGGER_THRESHOLD,
                    "trigger_roll_type": "world_eaters_total_carnage",
                    "requires_destroyed_by_melee_attack": True,
                    "requires_not_fought_this_phase": True,
                    "battle_round": state.battle_round,
                    "player_id": army.player_id,
                    "unit_instance_id": unit.unit_instance_id,
                    "model_instance_id": model.model_instance_id,
                    "requires_active_persisting_effect": {
                        "effect_kind": BLESSINGS_OF_KHORNE_EFFECT_KIND,
                        "source_rule_id": SOURCE_RULE_ID,
                        "owner_player_id": army.player_id,
                        "target_unit_instance_id": unit.unit_instance_id,
                        "battle_round": state.battle_round,
                        "selected_blessing_id": BlessingOfKhorne.TOTAL_CARNAGE.value,
                    },
                },
            )
            state.record_model_destruction_reaction_sources(
                model_instance_id=model.model_instance_id,
                sources=(*existing, source),
            )


def _profile_with_keyword_and_ability(
    profile: WeaponProfile,
    *,
    keyword: WeaponKeyword,
    ability: AbilityDescriptor,
) -> WeaponProfile:
    if type(profile) is not WeaponProfile:
        raise GameLifecycleError("Blessings weapon profile modifier requires WeaponProfile.")
    keywords = profile.keywords
    if keyword not in keywords:
        keywords = (*keywords, keyword)
    abilities = profile.abilities
    if all(existing.ability_id != ability.ability_id for existing in abilities):
        abilities = (*abilities, ability)
    source_ids = profile.source_ids
    if SOURCE_RULE_ID not in source_ids:
        source_ids = (*source_ids, SOURCE_RULE_ID)
    return replace(profile, keywords=keywords, abilities=abilities, source_ids=source_ids)


def _blessing_option(
    *,
    player_id: str,
    battle_round: int,
    dice_values: tuple[int, ...],
    selected: tuple[BlessingOfKhorne, ...],
    consumed: dict[BlessingOfKhorne, tuple[int, ...]],
    bloodshed_points: int,
) -> DecisionOption:
    option_suffix = "none" if not selected else "+".join(blessing.value for blessing in selected)
    labels = (
        "No Blessing"
        if not selected
        else ", ".join(_DEFINITIONS_BY_BLESSING[blessing].label for blessing in selected)
    )
    consumed_payload = {
        blessing.value: list(indices)
        for blessing, indices in sorted(consumed.items(), key=lambda item: item[0].value)
    }
    rules_update_sources = [UNBRIDLED_BLOODLUST_RULE_UPDATE_SOURCE]
    if bloodshed_points:
        rules_update_sources.append(ICON_OF_KHORNE_RULE_UPDATE_SOURCE)
    return DecisionOption(
        option_id=f"world_eaters:blessings:{option_suffix}",
        label=labels,
        payload=validate_json_value(
            {
                "submission_kind": "select_world_eaters_blessings",
                "player_id": player_id,
                "battle_round": battle_round,
                "faction_id": WORLD_EATERS_FACTION_ID,
                "source_rule_id": SOURCE_RULE_ID,
                "hook_id": HOOK_ID,
                "effect_kind": BLESSINGS_OF_KHORNE_EFFECT_KIND,
                "selected_blessing_ids": [blessing.value for blessing in selected],
                "selected_blessing_labels": [
                    _DEFINITIONS_BY_BLESSING[blessing].label for blessing in selected
                ],
                "dice_values": list(dice_values),
                "consumed_dice_by_blessing_id": consumed_payload,
                "bloodshed_points_spent": bloodshed_points,
                "rules_update_sources": rules_update_sources,
            }
        ),
    )


def _first_disjoint_pair_allocation(
    dice_values: tuple[int, ...],
    *,
    first: BlessingOfKhorne,
    second: BlessingOfKhorne,
) -> dict[BlessingOfKhorne, tuple[int, ...]] | None:
    first_allocations = _matching_allocations(dice_values, first)
    for first_allocation in first_allocations:
        second_allocation = _first_matching_allocation(
            dice_values,
            second,
            used_indices=first_allocation,
        )
        if second_allocation is None:
            continue
        return {first: first_allocation, second: second_allocation}
    return None


def _first_matching_allocation(
    dice_values: tuple[int, ...],
    blessing: BlessingOfKhorne,
    *,
    used_indices: tuple[int, ...],
) -> tuple[int, ...] | None:
    used = set(used_indices)
    for allocation in _matching_allocations(dice_values, blessing):
        if set(allocation).isdisjoint(used):
            return allocation
    return None


def _matching_allocations(
    dice_values: tuple[int, ...],
    blessing: BlessingOfKhorne,
) -> tuple[tuple[int, ...], ...]:
    definition = _DEFINITIONS_BY_BLESSING[_blessing_from_token(blessing)]
    allocations: list[tuple[int, ...]] = []
    for recipe in definition.recipes:
        for indices in combinations(range(len(dice_values)), recipe.count):
            values = tuple(dice_values[index] for index in indices)
            if min(values) < recipe.min_value:
                continue
            if len(set(values)) != 1:
                continue
            allocations.append(indices)
    return tuple(sorted(set(allocations), key=lambda item: (len(item), item)))


def _eligible_blessings_unit_ids_for_army(army: ArmyDefinition) -> tuple[str, ...]:
    if type(army) is not ArmyDefinition:
        raise GameLifecycleError("Blessings of Khorne requires an ArmyDefinition.")
    return tuple(
        unit.unit_instance_id for unit in army.units if _unit_has_blessings_of_khorne(unit)
    )


def _unit_has_blessings_of_khorne(unit: UnitInstance) -> bool:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("Blessings of Khorne requires a UnitInstance.")
    if _unit_has_keyword_token(unit.faction_keywords, WORLD_EATERS_FACTION_KEYWORD):
        return True
    return any(
        _normalise_rule_token(ability.name) == _normalise_rule_token("Blessings of Khorne")
        for ability in unit.datasheet_abilities
    )


def _target_unit_has_keyword(state: GameState, *, unit_instance_id: str, keyword: str) -> bool:
    unit, _army = _unit_and_army_by_id(state, unit_instance_id=unit_instance_id)
    return _unit_has_keyword_token((*unit.keywords, *unit.faction_keywords), keyword)


def _unit_has_keyword_token(values: tuple[str, ...], expected: str) -> bool:
    normalised_expected = _normalise_rule_token(expected)
    return any(_normalise_rule_token(value) == normalised_expected for value in values)


def _world_eaters_armies(state: GameState) -> tuple[ArmyDefinition, ...]:
    _validate_game_state(state)
    return tuple(
        army
        for army in state.army_definitions
        if army.detachment_selection.faction_id == WORLD_EATERS_FACTION_ID
    )


def _world_eaters_army_for_player(
    state: GameState,
    *,
    player_id: str,
) -> ArmyDefinition | None:
    requested_player_id = _validate_identifier("player_id", player_id)
    for army in _world_eaters_armies(state):
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
    raise GameLifecycleError("Blessings of Khorne unit_instance_id was not found.")


def _unit_owner_player_id(state: GameState, *, unit_instance_id: str) -> str:
    _unit, army = _unit_and_army_by_id(state, unit_instance_id=unit_instance_id)
    return army.player_id


@dataclass(frozen=True, slots=True)
class _DestroyedModelEvent:
    event_order: int
    event_id: str
    payload: dict[str, JsonValue]


def _last_blessings_selection_event_index(
    state: GameState,
    *,
    event_log: EventLog,
    player_id: str,
) -> int:
    last_index = -1
    for index, record in enumerate(event_log.records):
        if record.event_type != "world_eaters_blessings_of_khorne_selected":
            continue
        payload = record.payload
        if not isinstance(payload, dict):
            continue
        if payload.get("game_id") != state.game_id:
            continue
        if payload.get("player_id") != player_id:
            continue
        last_index = index
    return last_index


def _model_destroyed_events_after_index(
    state: GameState,
    *,
    event_log: EventLog,
    start_index: int,
) -> tuple[_DestroyedModelEvent, ...]:
    events: list[_DestroyedModelEvent] = []
    for index, record in enumerate(event_log.records):
        if index <= start_index:
            continue
        if record.event_type != "model_destroyed":
            continue
        payload = record.payload
        if not isinstance(payload, dict):
            continue
        if payload.get("game_id") != state.game_id:
            continue
        events.append(
            _DestroyedModelEvent(
                event_order=index,
                event_id=record.event_id,
                payload=payload,
            )
        )
    return tuple(events)


def _unit_destruction_completion_events(
    state: GameState,
    *,
    interval_events: tuple[_DestroyedModelEvent, ...],
) -> tuple[_DestroyedModelEvent, ...]:
    if state.battlefield_state is None:
        return ()
    removed_model_ids = set(state.battlefield_state.removed_model_ids)
    events_by_target_unit: dict[str, list[_DestroyedModelEvent]] = {}
    for event in interval_events:
        target_unit_id = _payload_string(event.payload, key="target_unit_instance_id")
        events_by_target_unit.setdefault(target_unit_id, []).append(event)
    completions: list[_DestroyedModelEvent] = []
    for target_unit_id, events in events_by_target_unit.items():
        target_unit, _target_army = _unit_and_army_by_id(state, unit_instance_id=target_unit_id)
        target_model_ids = {model.model_instance_id for model in target_unit.own_models}
        if not target_model_ids:
            continue
        if not target_model_ids <= removed_model_ids:
            continue
        completions.append(sorted(events, key=lambda event: event.event_order)[-1])
    return tuple(sorted(completions, key=lambda event: event.event_order))


def _unit_contains_icon_of_khorne_at_event(
    *,
    state: GameState,
    unit: UnitInstance,
    completion_event_order: int,
    interval_events: tuple[_DestroyedModelEvent, ...],
) -> bool:
    icon_bearers = tuple(
        model
        for model in unit.own_models
        if any(_is_icon_of_khorne_wargear_id(wargear_id) for wargear_id in model.wargear_ids)
    )
    return any(
        _model_was_live_at_event(
            state=state,
            model=model,
            completion_event_order=completion_event_order,
            interval_events=interval_events,
        )
        for model in icon_bearers
    )


def _model_was_live_at_event(
    *,
    state: GameState,
    model: ModelInstance,
    completion_event_order: int,
    interval_events: tuple[_DestroyedModelEvent, ...],
) -> bool:
    if state.battlefield_state is None:
        return model.is_alive
    removed_model_ids = set(state.battlefield_state.removed_model_ids)
    if model.model_instance_id not in removed_model_ids and model.is_alive:
        return True
    for event in interval_events:
        if _payload_string(event.payload, key="model_instance_id") != model.model_instance_id:
            continue
        return event.event_order > completion_event_order
    return False


def _is_icon_of_khorne_wargear_id(wargear_id: str) -> bool:
    token = _normalise_rule_token(wargear_id)
    return "ICON" in token and "KHORNE" in token


def _normalise_rule_token(value: str) -> str:
    return "".join(character for character in value.upper() if character.isalnum())


def _validate_dice_values(values: tuple[int, ...]) -> tuple[int, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("Blessings of Khorne dice values must be a tuple.")
    if len(values) < BLESSINGS_DICE_COUNT:
        raise GameLifecycleError("Blessings of Khorne requires at least eight dice.")
    validated: list[int] = []
    for value in values:
        if type(value) is not int or not 1 <= value <= 6:
            raise GameLifecycleError("Blessings of Khorne dice values must be D6 results.")
        validated.append(value)
    return tuple(validated)


def _payload_object(payload: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(payload, dict):
        raise GameLifecycleError("Blessings of Khorne payload must be an object.")
    return payload


def _payload_string(payload: dict[str, JsonValue], *, key: str) -> str:
    value = payload.get(key)
    if type(value) is not str or not value.strip():
        raise GameLifecycleError(f"Blessings of Khorne payload {key} must be a string.")
    return value


def _payload_string_list(payload: dict[str, JsonValue], *, key: str) -> tuple[str, ...]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise GameLifecycleError(f"Blessings of Khorne payload {key} must be a list.")
    strings: list[str] = []
    for item in value:
        if type(item) is not str or not item.strip():
            raise GameLifecycleError(f"Blessings of Khorne payload {key} must contain strings.")
        strings.append(item)
    return tuple(strings)


def _payload_int_list(payload: dict[str, JsonValue], *, key: str) -> tuple[int, ...]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise GameLifecycleError(f"Blessings of Khorne payload {key} must be a list.")
    integers: list[int] = []
    for item in value:
        if type(item) is not int:
            raise GameLifecycleError(f"Blessings of Khorne payload {key} must contain ints.")
        integers.append(item)
    return tuple(integers)


def _payload_index_mapping(
    payload: dict[str, JsonValue],
    *,
    key: str,
) -> dict[str, list[int]]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise GameLifecycleError(f"Blessings of Khorne payload {key} must be an object.")
    mapping: dict[str, list[int]] = {}
    for raw_blessing_id, raw_indices in value.items():
        if type(raw_blessing_id) is not str:
            raise GameLifecycleError(f"Blessings of Khorne payload {key} keys must be strings.")
        if not isinstance(raw_indices, list):
            raise GameLifecycleError(f"Blessings of Khorne payload {key} values must be lists.")
        indices: list[int] = []
        for raw_index in raw_indices:
            if type(raw_index) is not int or raw_index < 0:
                raise GameLifecycleError(
                    f"Blessings of Khorne payload {key} indices must be non-negative ints."
                )
            indices.append(raw_index)
        mapping[raw_blessing_id] = indices
    return mapping


def _payload_non_negative_int(payload: dict[str, JsonValue], *, key: str) -> int:
    value = payload.get(key)
    if type(value) is not int or value < 0:
        raise GameLifecycleError(f"Blessings of Khorne payload {key} must be non-negative int.")
    return value


def _blessing_from_token(token: object) -> BlessingOfKhorne:
    if type(token) is BlessingOfKhorne:
        return token
    if type(token) is not str:
        raise GameLifecycleError("Blessings of Khorne token must be a string.")
    try:
        return BlessingOfKhorne(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported Blessing of Khorne: {token}.") from exc


def _validate_game_state(state: object) -> None:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Blessings of Khorne requires GameState.")


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"Blessings of Khorne {field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"Blessings of Khorne {field_name} must not be empty.")
    return stripped
