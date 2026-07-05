from __future__ import annotations

from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.enhancement_effects import (
    EnhancementEffectBinding,
    EnhancementEffectContext,
    EnhancementPersistingEffectGrant,
)
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentContribution
from warhammer40k_core.engine.faction_content.common import (
    canonical_keyword as _canonical_keyword,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.ranged_rule_effects import (
    character_target_ap_bonus_payload,
    ranged_attacks_keep_hidden_payload,
)
from warhammer40k_core.engine.unit_factory import UnitInstance

from .rule import (
    AELDARI_FACTION_ID,
    PATH_OF_THE_OUTCAST_DETACHMENT_ID,
    RANGERS,
    SHROUD_RUNNERS,
)

CONTRIBUTION_ID = (
    "warhammer_40000_11th:aeldari:detachment:path_of_the_outcast:enhancements:scaffold"
)
SOURCE_RULE_ID = "phase17f:phase17e:aeldari:path-of-the-outcast:enhancements"
CAMOUFLAGED_SNIPERS_EFFECT_ID = (
    "warhammer_40000_11th:aeldari:detachment:path_of_the_outcast:camouflaged_snipers_upgrade"
)
CAMOUFLAGED_SNIPERS_ENHANCEMENT_ID = "aeldari:path-of-the-outcast:camouflaged-snipers-upgrade"
CAMOUFLAGED_SNIPERS_SOURCE_ID = (
    "gw-11e-faction-detachments-2026-27:enhancement:"
    "aeldari:path-of-the-outcast:camouflaged-snipers-upgrade"
)
ASSASSINS_EYE_EFFECT_ID = (
    "warhammer_40000_11th:aeldari:detachment:path_of_the_outcast:assassins_eye_upgrade"
)
ASSASSINS_EYE_ENHANCEMENT_ID = "aeldari:path-of-the-outcast:assassins-eye-upgrade"
ASSASSINS_EYE_SOURCE_ID = (
    "gw-11e-faction-detachments-2026-27:enhancement:"
    "aeldari:path-of-the-outcast:assassins-eye-upgrade"
)


def runtime_contribution() -> RuntimeContentContribution:
    return RuntimeContentContribution(
        contribution_id=CONTRIBUTION_ID,
        enhancement_effect_bindings=(
            EnhancementEffectBinding(
                effect_id=CAMOUFLAGED_SNIPERS_EFFECT_ID,
                source_id=SOURCE_RULE_ID,
                enhancement_id=CAMOUFLAGED_SNIPERS_ENHANCEMENT_ID,
                handler=camouflaged_snipers_effect,
            ),
            EnhancementEffectBinding(
                effect_id=ASSASSINS_EYE_EFFECT_ID,
                source_id=SOURCE_RULE_ID,
                enhancement_id=ASSASSINS_EYE_ENHANCEMENT_ID,
                handler=assassins_eye_effect,
            ),
        ),
    )


def camouflaged_snipers_effect(
    context: EnhancementEffectContext,
) -> tuple[EnhancementPersistingEffectGrant, ...]:
    if type(context) is not EnhancementEffectContext:
        raise GameLifecycleError("Camouflaged Snipers requires an EnhancementEffectContext.")
    if context.assignment.enhancement_id != CAMOUFLAGED_SNIPERS_ENHANCEMENT_ID:
        return ()
    _validate_path_of_the_outcast_army(context.army, label="Camouflaged Snipers")
    unit = context.target_unit
    if not _unit_has_keyword(unit, RANGERS):
        raise GameLifecycleError("Camouflaged Snipers requires a RANGERS unit.")
    effect = PersistingEffect(
        effect_id=f"{CAMOUFLAGED_SNIPERS_EFFECT_ID}:{unit.unit_instance_id}",
        source_rule_id=SOURCE_RULE_ID,
        owner_player_id=context.army.player_id,
        target_unit_instance_ids=(unit.unit_instance_id,),
        started_battle_round=context.state.battle_round,
        started_phase=None,
        expiration=EffectExpiration.end_of_battle(),
        effect_payload=ranged_attacks_keep_hidden_payload(
            enhancement_id=CAMOUFLAGED_SNIPERS_ENHANCEMENT_ID,
            assignment_source_id=context.assignment.source_id,
        ),
    )
    return (
        EnhancementPersistingEffectGrant(
            effect_id=CAMOUFLAGED_SNIPERS_EFFECT_ID,
            source_id=SOURCE_RULE_ID,
            enhancement_id=CAMOUFLAGED_SNIPERS_ENHANCEMENT_ID,
            target_unit_instance_id=unit.unit_instance_id,
            persisting_effect=effect,
            replay_payload={
                "effect_kind": "camouflaged_snipers_upgrade",
                "enhancement_source_id": CAMOUFLAGED_SNIPERS_SOURCE_ID,
                "target_unit_instance_id": unit.unit_instance_id,
                "required_keyword": RANGERS,
            },
        ),
    )


def assassins_eye_effect(
    context: EnhancementEffectContext,
) -> tuple[EnhancementPersistingEffectGrant, ...]:
    if type(context) is not EnhancementEffectContext:
        raise GameLifecycleError("Assassins' Eye requires an EnhancementEffectContext.")
    if context.assignment.enhancement_id != ASSASSINS_EYE_ENHANCEMENT_ID:
        return ()
    _validate_path_of_the_outcast_army(context.army, label="Assassins' Eye")
    unit = context.target_unit
    if not (_unit_has_keyword(unit, RANGERS) or _unit_has_keyword(unit, SHROUD_RUNNERS)):
        raise GameLifecycleError("Assassins' Eye requires RANGERS or SHROUD RUNNERS.")
    effect = PersistingEffect(
        effect_id=f"{ASSASSINS_EYE_EFFECT_ID}:{unit.unit_instance_id}",
        source_rule_id=SOURCE_RULE_ID,
        owner_player_id=context.army.player_id,
        target_unit_instance_ids=(unit.unit_instance_id,),
        started_battle_round=context.state.battle_round,
        started_phase=None,
        expiration=EffectExpiration.end_of_battle(),
        effect_payload=character_target_ap_bonus_payload(
            enhancement_id=ASSASSINS_EYE_ENHANCEMENT_ID,
            assignment_source_id=context.assignment.source_id,
            ap_bonus=1,
        ),
    )
    return (
        EnhancementPersistingEffectGrant(
            effect_id=ASSASSINS_EYE_EFFECT_ID,
            source_id=SOURCE_RULE_ID,
            enhancement_id=ASSASSINS_EYE_ENHANCEMENT_ID,
            target_unit_instance_id=unit.unit_instance_id,
            persisting_effect=effect,
            replay_payload={
                "effect_kind": "assassins_eye_upgrade",
                "enhancement_source_id": ASSASSINS_EYE_SOURCE_ID,
                "target_unit_instance_id": unit.unit_instance_id,
                "required_keywords_any": [RANGERS, SHROUD_RUNNERS],
                "target_required_keyword": "CHARACTER",
                "armor_penetration_bonus": 1,
            },
        ),
    )


def _validate_path_of_the_outcast_army(army: ArmyDefinition, *, label: str) -> None:
    if type(army) is not ArmyDefinition:
        raise GameLifecycleError(f"{label} requires an ArmyDefinition.")
    if not (
        army.detachment_selection.faction_id == AELDARI_FACTION_ID
        and PATH_OF_THE_OUTCAST_DETACHMENT_ID in army.detachment_selection.detachment_ids
    ):
        raise GameLifecycleError(f"{label} requires Path of the Outcast.")


def _unit_has_keyword(unit: UnitInstance, keyword: str) -> bool:
    canonical = _canonical_keyword(keyword)
    return any(_canonical_keyword(stored) == canonical for stored in unit.keywords)
