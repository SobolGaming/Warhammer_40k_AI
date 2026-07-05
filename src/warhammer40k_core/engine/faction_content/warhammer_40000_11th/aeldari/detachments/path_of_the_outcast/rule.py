from __future__ import annotations

from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentContribution
from warhammer40k_core.engine.faction_content.common import (
    canonical_keyword as _canonical_keyword,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.ranged_rule_effects import detection_range_bonus_payload
from warhammer40k_core.engine.shooting_unit_selected_hooks import (
    ShootingUnitSelectedContext,
    ShootingUnitSelectedEffectGrant,
    ShootingUnitSelectedHookBinding,
)
from warhammer40k_core.engine.unit_factory import UnitInstance

CONTRIBUTION_ID = "warhammer_40000_11th:aeldari:detachment:path_of_the_outcast:rule:scaffold"
FAR_REACHING_DOOM_SOURCE_RULE_ID = "phase17f:phase17e:aeldari:path-of-the-outcast:far-reaching-doom"
FAR_REACHING_DOOM_EFFECT_KIND = "aeldari_path_of_the_outcast_far_reaching_doom"
FAR_REACHING_DOOM_HOOK_ID = (
    "warhammer_40000_11th:aeldari:path_of_the_outcast:far_reaching_doom:selected_shooting_unit"
)
AELDARI_FACTION_ID = "aeldari"
PATH_OF_THE_OUTCAST_DETACHMENT_ID = "path-of-the-outcast"
RANGERS = "RANGERS"
SHROUD_RUNNERS = "SHROUD RUNNERS"


def runtime_contribution() -> RuntimeContentContribution:
    return RuntimeContentContribution(
        contribution_id=CONTRIBUTION_ID,
        shooting_unit_selected_hook_bindings=(
            ShootingUnitSelectedHookBinding(
                hook_id=FAR_REACHING_DOOM_HOOK_ID,
                source_id=FAR_REACHING_DOOM_SOURCE_RULE_ID,
                handler=apply_far_reaching_doom,
            ),
        ),
    )


def apply_far_reaching_doom(
    context: ShootingUnitSelectedContext,
) -> tuple[ShootingUnitSelectedEffectGrant, ...]:
    if type(context) is not ShootingUnitSelectedContext:
        raise GameLifecycleError("Far-reaching Doom requires a shooting-unit-selected context.")
    army = context.state.army_definition_for_player(context.player_id)
    if army is None:
        raise GameLifecycleError("Far-reaching Doom requires selected player's army.")
    if army.detachment_selection.faction_id != AELDARI_FACTION_ID:
        return ()
    if PATH_OF_THE_OUTCAST_DETACHMENT_ID not in army.detachment_selection.detachment_ids:
        return ()
    unit = _unit_in_army(army_units=army.units, unit_instance_id=context.unit_instance_id)
    if not (_unit_has_keyword(unit, RANGERS) or _unit_has_keyword(unit, SHROUD_RUNNERS)):
        return ()
    target_unit_ids = _enemy_placed_unit_ids(context=context)
    if not target_unit_ids:
        return ()
    effect = PersistingEffect(
        effect_id=f"{context.result_id}:far-reaching-doom",
        source_rule_id=FAR_REACHING_DOOM_SOURCE_RULE_ID,
        owner_player_id=context.player_id,
        target_unit_instance_ids=target_unit_ids,
        started_battle_round=context.battle_round,
        started_phase=BattlePhase.SHOOTING,
        expiration=EffectExpiration.end_phase(
            battle_round=context.battle_round,
            phase=BattlePhase.SHOOTING,
            player_id=context.player_id,
        ),
        effect_payload=detection_range_bonus_payload(
            bonus_inches=6,
            source_rule_kind=FAR_REACHING_DOOM_EFFECT_KIND,
            source_unit_instance_id=context.unit_instance_id,
            source_decision_request_id=context.request_id,
            source_decision_result_id=context.result_id,
            expires_when_source_unit_has_shot=True,
        ),
    )
    return (
        ShootingUnitSelectedEffectGrant(
            hook_id=FAR_REACHING_DOOM_HOOK_ID,
            source_id=FAR_REACHING_DOOM_SOURCE_RULE_ID,
            unit_instance_id=context.unit_instance_id,
            persisting_effect=effect,
            event_type="far_reaching_doom_detection_range_granted",
            replay_payload={
                "shooting_unit_instance_id": context.unit_instance_id,
                "target_unit_instance_ids": list(target_unit_ids),
            },
        ),
    )


def _unit_in_army(
    *,
    army_units: tuple[UnitInstance, ...],
    unit_instance_id: str,
) -> UnitInstance:
    for unit in army_units:
        if unit.unit_instance_id == unit_instance_id:
            return unit
    raise GameLifecycleError("Far-reaching Doom selected unit is not in the player's army.")


def _enemy_placed_unit_ids(*, context: ShootingUnitSelectedContext) -> tuple[str, ...]:
    battlefield_state = context.state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Far-reaching Doom requires battlefield state.")
    target_ids: list[str] = []
    for placed_army in battlefield_state.placed_armies:
        if placed_army.player_id == context.player_id:
            continue
        target_ids.extend(placement.unit_instance_id for placement in placed_army.unit_placements)
    return tuple(sorted(target_ids))


def _unit_has_keyword(unit: UnitInstance, keyword: str) -> bool:
    canonical = _canonical_keyword(keyword)
    return canonical in {_canonical_keyword(unit_keyword) for unit_keyword in unit.keywords}
