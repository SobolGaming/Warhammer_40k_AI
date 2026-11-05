"""Capture an enemy's eligibility when selected to fight, before any pile-in."""

from dataclasses import dataclass
from functools import partial

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.core.weapon_profiles import RangeProfileKind
from warhammer40k_core.engine.ability_presence import active_ability_model_ids_for_unit
from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.fight_unit_selected_hooks import (
    FightUnitSelectedContext,
    FightUnitSelectedEffectGrant,
    FightUnitSelectedHookBinding,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.physical_engagement import (
    scenario_rules_units_are_physically_engaged,
)
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.runtime_modifiers import HitRollModifierContext

EFFECT_KIND = "enemy_selected_fight_hit_modifier"
_identifier = IdentifierValidator(GameLifecycleError)


@dataclass(frozen=True, slots=True)
class EnemySelectedFightHitModifier:
    """A source-backed static datasheet ability with an end-of-phase melee modifier."""

    ability_id: str
    modifier_id: str
    operand: int
    excluded_keyword_tokens: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _identifier("ability_id", self.ability_id)
        _identifier("modifier_id", self.modifier_id)
        if type(self.operand) is not int or self.operand == 0:
            raise GameLifecycleError("Selected-fight modifier requires a nonzero integer operand.")
        if type(self.excluded_keyword_tokens) is not tuple:
            raise GameLifecycleError("Selected-fight exclusions require canonical keyword tokens.")
        for token in self.excluded_keyword_tokens:
            _identifier("excluded_keyword_token", token)

    def selection_binding(self) -> FightUnitSelectedHookBinding:
        return FightUnitSelectedHookBinding(
            hook_id=f"{self.modifier_id}:selected-to-fight",
            source_id=self.ability_id,
            handler=partial(capture_enemy_selected_fight_modifier, self),
        )


def capture_enemy_selected_fight_modifier(
    descriptor: EnemySelectedFightHitModifier,
    context: FightUnitSelectedContext,
) -> tuple[FightUnitSelectedEffectGrant, ...]:
    if type(context) is not FightUnitSelectedContext:
        raise GameLifecycleError("Selected-fight capture requires a FightUnitSelectedContext.")
    state = context.state
    selected = rules_unit_view_by_id(state=state, unit_instance_id=context.unit_instance_id)
    if selected.owner_player_id != context.player_id:
        raise GameLifecycleError("Selected-fight capture actor does not own the selected unit.")
    if set(descriptor.excluded_keyword_tokens).intersection(selected.keywords):
        return ()
    if state.active_player_id is None:
        raise GameLifecycleError("Selected-fight capture requires an active turn owner.")
    scenario = battlefield_scenario_for_state(state=state)
    grants: list[FightUnitSelectedEffectGrant] = []
    for army in state.army_definitions:
        if army.player_id == selected.owner_player_id:
            continue
        source_ids: set[str] = set()
        for unit in army.units:
            if not any(a.ability_id == descriptor.ability_id for a in unit.datasheet_abilities):
                continue
            if not active_ability_model_ids_for_unit(state=state, unit=unit):
                continue
            source = rules_unit_view_by_id(state=state, unit_instance_id=unit.unit_instance_id)
            if scenario_rules_units_are_physically_engaged(
                scenario=scenario,
                ruleset_descriptor=state.runtime_ruleset_descriptor(),
                first_unit_instance_id=source.unit_instance_id,
                second_unit_instance_id=selected.unit_instance_id,
            ):
                source_ids.add(source.unit_instance_id)
        if not source_ids:
            continue
        effect = PersistingEffect(
            effect_id=f"{descriptor.modifier_id}:{context.result_id}:{army.player_id}",
            source_rule_id=descriptor.ability_id,
            owner_player_id=army.player_id,
            target_unit_instance_ids=(selected.unit_instance_id,),
            started_battle_round=context.battle_round,
            started_phase=context.source_phase,
            expiration=EffectExpiration.end_phase(
                battle_round=context.battle_round,
                phase=context.source_phase,
                player_id=state.active_player_id,
            ),
            effect_payload=validate_json_value(
                {
                    "effect_kind": EFFECT_KIND,
                    "modifier_id": descriptor.modifier_id,
                    "operand": descriptor.operand,
                    "selection_request_id": context.request_id,
                    "selection_result_id": context.result_id,
                    "source_unit_instance_ids": sorted(source_ids),
                }
            ),
        )
        grants.append(
            FightUnitSelectedEffectGrant(
                hook_id=f"{descriptor.modifier_id}:selected-to-fight",
                source_id=descriptor.ability_id,
                unit_instance_id=selected.unit_instance_id,
                persisting_effect=effect,
            )
        )
    return tuple(grants)


def captured_enemy_selected_fight_hit_modifier(
    descriptor: EnemySelectedFightHitModifier,
    context: HitRollModifierContext,
) -> int:
    if type(context) is not HitRollModifierContext:
        raise GameLifecycleError("Selected-fight modifier requires a HitRollModifierContext.")
    if context.weapon_profile.range_profile.kind is not RangeProfileKind.MELEE:
        return 0
    effects = context.state.persisting_effects_for_unit(context.attacking_unit_instance_id)
    applicable = False
    for effect in effects:
        if effect.source_rule_id != descriptor.ability_id:
            continue
        payload = effect.effect_payload
        if (
            type(payload) is not dict
            or payload.get("effect_kind") != EFFECT_KIND
            or payload.get("modifier_id") != descriptor.modifier_id
            or type(payload.get("operand")) is not int
            or payload["operand"] != descriptor.operand
        ):
            raise GameLifecycleError("Captured selected-fight modifier payload drifted.")
        applicable = True
    # One or more qualifying sources establish the same modifier once.
    return descriptor.operand if applicable else 0
