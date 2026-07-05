from __future__ import annotations

from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentContribution
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.stratagems import (
    GENERIC_RULE_IR_STRATAGEM_HANDLER_ID,
    JUST_SHOT_UNIT_TARGET_POLICY_ID,
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
    faction_court_of_the_phoenician_ir_support_2026_27 as court_ir,
)

CONTRIBUTION_ID = (
    "warhammer_40000_11th:emperors_children:detachment:court_of_the_phoenician:stratagems:rule_ir"
)
DETACHMENT_ID = "court-of-the-phoenician"
PROFILE_PREFIX = "phase17s:stratagem:emperors-children:court-of-the-phoenician"

CONTEMPTUOUS_DISREGARD_ID = "000010655002"
PRIDEFUL_SUPERIORITY_ID = "000010655003"
SINUOUS_BREACH_ID = "000010655004"
CLOSE_QUARTERS_EXCRUCIATION_ID = "000010655005"
EUPHORIC_INSPIRATION_ID = "000010655006"
CATALYTIC_STIMULUS_ID = "000010655007"


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
                    stratagem_id=CONTEMPTUOUS_DISREGARD_ID,
                    record_suffix="shooting",
                    name="CONTEMPTUOUS DISREGARD",
                    category=StratagemCategory.BATTLE_TACTIC,
                    trigger_kind=TimingTriggerKind.START_PHASE,
                    phase=BattlePhase.SHOOTING,
                    target_descriptor="one_friendly_emperors_children_unit",
                    when_descriptor="either_players_shooting_phase_attack_targets_unit",
                    effect_descriptor="wound_roll_minus_one_when_strength_exceeds_toughness",
                ),
                _stratagem_record(
                    stratagem_id=CONTEMPTUOUS_DISREGARD_ID,
                    record_suffix="fight",
                    name="CONTEMPTUOUS DISREGARD",
                    category=StratagemCategory.BATTLE_TACTIC,
                    trigger_kind=TimingTriggerKind.START_PHASE,
                    phase=BattlePhase.FIGHT,
                    target_descriptor="one_friendly_emperors_children_unit",
                    when_descriptor="either_players_fight_phase_attack_targets_unit",
                    effect_descriptor="wound_roll_minus_one_when_strength_exceeds_toughness",
                ),
                _stratagem_record(
                    stratagem_id=PRIDEFUL_SUPERIORITY_ID,
                    name="PRIDEFUL SUPERIORITY",
                    category=StratagemCategory.BATTLE_TACTIC,
                    trigger_kind=TimingTriggerKind.START_PHASE,
                    phase=BattlePhase.FIGHT,
                    target_descriptor="one_friendly_emperors_children_unit",
                    when_descriptor="either_players_fight_phase_unit_fights",
                    effect_descriptor="hit_and_wound_rerolls_against_character_targets",
                ),
                _stratagem_record(
                    stratagem_id=SINUOUS_BREACH_ID,
                    record_suffix="movement",
                    name="SINUOUS BREACH",
                    category=StratagemCategory.STRATEGIC_PLOY,
                    trigger_kind=TimingTriggerKind.START_PHASE,
                    phase=BattlePhase.MOVEMENT,
                    target_descriptor="one_friendly_emperors_children_daemon_unit",
                    when_descriptor="your_movement_phase_unit_makes_normal_or_advance_move",
                    effect_descriptor="horizontal_terrain_transit",
                    required_keywords=(court_ir.DAEMON_KEYWORD,),
                ),
                _stratagem_record(
                    stratagem_id=SINUOUS_BREACH_ID,
                    record_suffix="charge",
                    name="SINUOUS BREACH",
                    category=StratagemCategory.STRATEGIC_PLOY,
                    trigger_kind=TimingTriggerKind.START_PHASE,
                    phase=BattlePhase.CHARGE,
                    target_descriptor="one_friendly_emperors_children_daemon_unit",
                    when_descriptor="your_charge_phase_unit_makes_charge_move",
                    effect_descriptor="horizontal_terrain_transit",
                    required_keywords=(court_ir.DAEMON_KEYWORD,),
                ),
                _stratagem_record(
                    stratagem_id=CLOSE_QUARTERS_EXCRUCIATION_ID,
                    name="CLOSE-QUARTERS EXCRUCIATION",
                    category=StratagemCategory.BATTLE_TACTIC,
                    trigger_kind=TimingTriggerKind.START_PHASE,
                    phase=BattlePhase.SHOOTING,
                    target_descriptor="one_friendly_emperors_children_unit",
                    when_descriptor="your_shooting_phase_unit_makes_attacks",
                    effect_descriptor="strength_and_ap_plus_one_within_12",
                ),
                _stratagem_record(
                    stratagem_id=EUPHORIC_INSPIRATION_ID,
                    name="EUPHORIC INSPIRATION",
                    category=StratagemCategory.STRATEGIC_PLOY,
                    trigger_kind=TimingTriggerKind.START_PHASE,
                    phase=BattlePhase.CHARGE,
                    target_descriptor="one_friendly_emperors_children_daemon_unit",
                    when_descriptor="your_charge_phase",
                    effect_descriptor="charge_reroll_aura",
                    required_keywords=(court_ir.DAEMON_KEYWORD,),
                ),
                _stratagem_record(
                    stratagem_id=CATALYTIC_STIMULUS_ID,
                    name="CATALYTIC STIMULUS",
                    category=StratagemCategory.STRATEGIC_PLOY,
                    trigger_kind=TimingTriggerKind.JUST_AFTER_ENEMY_UNIT_HAS_SHOT,
                    phase=BattlePhase.SHOOTING,
                    target_policy_id=JUST_SHOT_UNIT_TARGET_POLICY_ID,
                    target_descriptor="one_friendly_emperors_children_unit_that_was_shot",
                    when_descriptor="opponents_shooting_phase_after_unit_loses_wounds",
                    effect_descriptor="surge_normal_move_d6",
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
    target_descriptor: str,
    when_descriptor: str,
    effect_descriptor: str,
    record_suffix: str | None = None,
    target_policy_id: str = "friendly_unit",
    required_keywords: tuple[str, ...] = (),
) -> StratagemCatalogRecord:
    profile_id = f"{PROFILE_PREFIX}:{stratagem_id}"
    rule_ir_payload = court_ir.stratagem_activation_rule_ir_payload_by_profile_id(profile_id)
    if rule_ir_payload is None:
        raise GameLifecycleError("Court of the Phoenician Stratagem RuleIR payload is missing.")
    source_id = (
        "gw-11e-phase17e-exact-faction-subrules-2026-27:"
        f"stratagem:emperors-children:court-of-the-phoenician:{stratagem_id}"
    )
    record_id = profile_id if record_suffix is None else f"{profile_id}:{record_suffix}"
    return StratagemCatalogRecord(
        record_id=record_id,
        definition=StratagemDefinition(
            stratagem_id=stratagem_id,
            name=name,
            source_id=source_id,
            command_point_cost=1,
            category=category,
            when_descriptor=when_descriptor,
            target_descriptor=target_descriptor,
            effect_descriptor=effect_descriptor,
            restrictions_descriptor="matched_play_same_stratagem_per_phase",
            timing=StratagemTimingDescriptor(trigger_kind=trigger_kind, phase=phase),
            restriction_policy=StratagemRestrictionPolicy(),
            target_spec=StratagemTargetSpec(
                target_kind=StratagemTargetKind.FRIENDLY_UNIT,
                target_policy_id=target_policy_id,
                required_keywords=required_keywords,
                required_faction_keywords=(court_ir.EMPERORS_CHILDREN_KEYWORD,),
            ),
            handler_id=GENERIC_RULE_IR_STRATAGEM_HANDLER_ID,
            effect_payload=validate_json_value({"rule_ir": rule_ir_payload}),
        ),
        availability_kind=StratagemAvailabilityKind.DETACHMENT,
        detachment_id=DETACHMENT_ID,
    )
