from __future__ import annotations

from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentContribution
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.stratagems import (
    ENGAGED_WITH_FALL_BACK_UNIT_TARGET_POLICY_ID,
    GENERIC_RULE_IR_STRATAGEM_HANDLER_ID,
    StratagemAvailabilityKind,
    StratagemCatalogRecord,
    StratagemCategory,
    StratagemDefinition,
    StratagemRestrictionPolicy,
    StratagemTargetKind,
    StratagemTargetSpec,
    StratagemTimingDescriptor,
)
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_spectacle_of_slaughter_ir_support_2026_27 as spectacle_ir,
)

CONTRIBUTION_ID = (
    "warhammer_40000_11th:emperors_children:detachment:spectacle_of_slaughter:stratagems:rule_ir"
)
DETACHMENT_ID = "spectacle-of-slaughter"
PROFILE_PREFIX = "phase17s:stratagem:emperors-children:spectacle-of-slaughter"
FLAWLESS_BLADES_KEYWORD = spectacle_ir.FLAWLESS_BLADES_KEYWORD

HONOUR_IS_FOR_FOOLS_ID = "000010901002"
SINGLE_MINDED_STRIKE_ID = "000010901003"
INTOXICATED_BY_TRIUMPH_ID = "000010901004"


def runtime_contribution() -> RuntimeContentContribution:
    return RuntimeContentContribution(
        contribution_id=CONTRIBUTION_ID,
        stratagem_records=_stratagem_records(),
    )


def _stratagem_records() -> tuple[StratagemCatalogRecord, ...]:
    return tuple(
        sorted(
            (
                _stratagem_record(
                    stratagem_id=HONOUR_IS_FOR_FOOLS_ID,
                    name="HONOUR IS FOR FOOLS",
                    category=StratagemCategory.BATTLE_TACTIC,
                    trigger_kind=TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_SELECTED_TO_FIGHT,
                    phase=BattlePhase.FIGHT,
                    target_policy_id="friendly_unit",
                    when_descriptor="fight_phase_selected_to_fight",
                    effect_descriptor="melee_precision_until_end_phase",
                ),
                _stratagem_record(
                    stratagem_id=SINGLE_MINDED_STRIKE_ID,
                    name="SINGLE-MINDED STRIKE",
                    category=StratagemCategory.STRATEGIC_PLOY,
                    trigger_kind=TimingTriggerKind.DURING_PHASE,
                    phase=BattlePhase.CHARGE,
                    target_policy_id="friendly_unit",
                    when_descriptor="charge_phase_unit_starts_charge_move",
                    effect_descriptor="charge_move_through_non_vehicle_monster_models",
                ),
                _stratagem_record(
                    stratagem_id=INTOXICATED_BY_TRIUMPH_ID,
                    name="INTOXICATED BY TRIUMPH",
                    category=StratagemCategory.STRATEGIC_PLOY,
                    trigger_kind=TimingTriggerKind.AFTER_ENEMY_UNIT_ENDS_MOVE,
                    phase=BattlePhase.MOVEMENT,
                    target_policy_id=ENGAGED_WITH_FALL_BACK_UNIT_TARGET_POLICY_ID,
                    when_descriptor="opponent_movement_phase_enemy_ends_fall_back",
                    effect_descriptor="triggered_normal_move_d3_plus_3",
                ),
            ),
            key=lambda record: record.record_id,
        )
    )


def _stratagem_record(
    *,
    stratagem_id: str,
    name: str,
    category: StratagemCategory,
    trigger_kind: TimingTriggerKind,
    phase: BattlePhase,
    target_policy_id: str,
    when_descriptor: str,
    effect_descriptor: str,
) -> StratagemCatalogRecord:
    profile_id = f"{PROFILE_PREFIX}:{stratagem_id}"
    rule_ir_payload = spectacle_ir.stratagem_activation_rule_ir_payload_by_profile_id(profile_id)
    if rule_ir_payload is None:
        raise GameLifecycleError("Spectacle of Slaughter Stratagem RuleIR payload is missing.")
    source_id = (
        "gw-11e-phase17e-exact-faction-subrules-2026-27:"
        f"stratagem:emperors-children:spectacle-of-slaughter:{stratagem_id}"
    )
    return StratagemCatalogRecord(
        record_id=profile_id,
        definition=StratagemDefinition(
            stratagem_id=stratagem_id,
            name=name,
            source_id=source_id,
            command_point_cost=1,
            category=category,
            when_descriptor=when_descriptor,
            target_descriptor="one_friendly_flawless_blades_unit",
            effect_descriptor=effect_descriptor,
            restrictions_descriptor="matched_play_same_stratagem_per_phase",
            timing=StratagemTimingDescriptor(trigger_kind=trigger_kind, phase=phase),
            restriction_policy=StratagemRestrictionPolicy(),
            target_spec=StratagemTargetSpec(
                target_kind=StratagemTargetKind.FRIENDLY_UNIT,
                target_policy_id=target_policy_id,
                required_faction_keywords=(FLAWLESS_BLADES_KEYWORD,),
            ),
            handler_id=GENERIC_RULE_IR_STRATAGEM_HANDLER_ID,
            effect_payload=validate_json_value({"rule_ir": rule_ir_payload}),
        ),
        availability_kind=StratagemAvailabilityKind.DETACHMENT,
        detachment_id=DETACHMENT_ID,
    )
