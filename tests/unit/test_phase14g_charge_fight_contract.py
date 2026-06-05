from __future__ import annotations

import json
from dataclasses import replace
from typing import cast

import pytest

from warhammer40k_core.core.ruleset_descriptor import (
    ChargeEndpointRequirement,
    ChargePolicyDescriptor,
    ChargeTargetSelectionTiming,
    ConsolidationModeKind,
    FightEligibilityKind,
    FightOrderingBandKind,
    FightPhaseStepKind,
    FightPolicyDescriptor,
    FightTypeKind,
    RulesetDescriptor,
    RulesetDescriptorError,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import core_stratagems


def test_phase14g_charge_policy_freezes_after_roll_target_contract() -> None:
    descriptor = RulesetDescriptor.warhammer_40000_eleventh()
    charge_policy = descriptor.charge_policy
    payload = charge_policy.to_payload()
    encoded = json.dumps(payload, sort_keys=True)

    assert charge_policy.target_selection_timing is ChargeTargetSelectionTiming.AFTER_ROLL
    assert charge_policy.endpoint_requirement is (
        ChargeEndpointRequirement.SELECTED_TARGET_ENGAGEMENT
    )
    assert charge_policy.max_declaration_range_inches == 12.0
    assert charge_policy.max_target_selection_range_inches == 12.0
    assert charge_policy.target_selection_requires_rolled_distance
    assert charge_policy.requires_unengaged_unit
    assert charge_policy.forbids_advance
    assert charge_policy.forbids_fall_back
    assert charge_policy.requires_battlefield_presence
    assert charge_policy.must_end_closer_to_selected_targets
    assert charge_policy.preferred_target_distance_inches == 1.0
    assert charge_policy.must_reach_preferred_target_distance_if_possible
    assert charge_policy.must_end_engaged_if_possible
    assert charge_policy.must_end_engaged_with_every_selected_target
    assert charge_policy.forbids_non_target_engagement
    assert charge_policy.grants_fights_first_until_end_turn
    assert "<" not in encoded
    assert "object at 0x" not in encoded
    assert ChargePolicyDescriptor.from_payload(payload).to_payload() == payload


def test_phase14g_fight_policy_freezes_sequence_ordering_and_modes() -> None:
    fight_policy = RulesetDescriptor.warhammer_40000_eleventh().fight_policy
    payload = fight_policy.to_payload()
    encoded = json.dumps(payload, sort_keys=True)

    assert fight_policy.steps == (
        FightPhaseStepKind.START,
        FightPhaseStepKind.PILE_IN,
        FightPhaseStepKind.FIGHT,
        FightPhaseStepKind.CONSOLIDATE,
        FightPhaseStepKind.END,
    )
    assert fight_policy.eligibility_kinds == (
        FightEligibilityKind.CHARGED_THIS_TURN,
        FightEligibilityKind.CURRENTLY_ENGAGED,
        FightEligibilityKind.ENGAGED_AT_FIGHT_STEP_START,
    )
    assert fight_policy.ordering_bands == (
        FightOrderingBandKind.FIGHTS_FIRST,
        FightOrderingBandKind.REMAINING_COMBATS,
    )
    assert fight_policy.pile_in_available_to_both_players
    assert fight_policy.consolidation_available_to_both_players
    assert fight_policy.active_player_pile_in_first
    assert fight_policy.active_player_consolidates_first
    assert fight_policy.fights_first_alternates
    assert fight_policy.remaining_combats_alternates
    assert fight_policy.eligible_pass_distance_inches == 5.0
    assert fight_policy.fight_types == (FightTypeKind.NORMAL, FightTypeKind.OVERRUN)
    assert fight_policy.consolidation_modes == (
        ConsolidationModeKind.ONGOING,
        ConsolidationModeKind.ENGAGING,
        ConsolidationModeKind.OBJECTIVE,
    )
    assert fight_policy.engaging_consolidation_emits_opponent_fight_decision
    assert "<" not in encoded
    assert "object at 0x" not in encoded
    assert FightPolicyDescriptor.from_payload(payload).to_payload() == payload


def test_phase14g_descriptor_hash_includes_charge_and_fight_contracts() -> None:
    descriptor = RulesetDescriptor.warhammer_40000_eleventh()
    changed_charge = replace(
        descriptor,
        charge_policy=ChargePolicyDescriptor(
            target_selection_timing=ChargeTargetSelectionTiming.BEFORE_ROLL,
            endpoint_requirement=ChargeEndpointRequirement.DECLARED_TARGET_ENGAGEMENT,
        ),
        descriptor_hash="",
    )
    changed_fight = replace(
        descriptor,
        fight_policy=replace(
            descriptor.fight_policy,
            eligible_pass_distance_inches=6.0,
        ),
        descriptor_hash="",
    )
    payload = descriptor.to_payload()
    payload["fight_policy"]["eligible_pass_distance_inches"] = 6.0

    assert changed_charge.descriptor_hash != descriptor.descriptor_hash
    assert changed_fight.descriptor_hash != descriptor.descriptor_hash
    with pytest.raises(RulesetDescriptorError, match="descriptor_hash"):
        RulesetDescriptor.from_payload(payload)


def test_phase14g_contract_payloads_reject_malformed_values() -> None:
    with pytest.raises(RulesetDescriptorError, match="target range"):
        ChargePolicyDescriptor(
            target_selection_timing=ChargeTargetSelectionTiming.AFTER_ROLL,
            endpoint_requirement=ChargeEndpointRequirement.SELECTED_TARGET_ENGAGEMENT,
            max_declaration_range_inches=10.0,
            max_target_selection_range_inches=12.0,
        )

    with pytest.raises(RulesetDescriptorError, match="forbids_advance"):
        ChargePolicyDescriptor(
            target_selection_timing=ChargeTargetSelectionTiming.AFTER_ROLL,
            endpoint_requirement=ChargeEndpointRequirement.SELECTED_TARGET_ENGAGEMENT,
            forbids_advance=cast(bool, "yes"),
        )

    duplicate_step_payload = FightPolicyDescriptor.warhammer_40000_eleventh_default().to_payload()
    duplicate_step_payload["steps"] = [
        FightPhaseStepKind.START.value,
        FightPhaseStepKind.START.value,
    ]
    with pytest.raises(RulesetDescriptorError, match="duplicates"):
        FightPolicyDescriptor.from_payload(duplicate_step_payload)

    invalid_distance_payload = FightPolicyDescriptor.warhammer_40000_eleventh_default().to_payload()
    invalid_distance_payload["eligible_pass_distance_inches"] = 0.0
    with pytest.raises(RulesetDescriptorError, match="greater than 0"):
        FightPolicyDescriptor.from_payload(invalid_distance_payload)


def test_phase14g_charge_fight_core_stratagem_hooks_remain_deferred() -> None:
    deferred = {
        row.stratagem_id: (row.target_policy_id, row.handler_id)
        for row in core_stratagems.core_stratagem_rows()
        if row.stratagem_id
        in {"counteroffensive", "crushing-impact", "epic-challenge", "heroic-intervention"}
    }

    assert deferred == {
        "counteroffensive": (
            "unsupported:phase-14g:fight-order-interrupt-unit",
            "unsupported:phase-14g:counteroffensive",
        ),
        "crushing-impact": (
            "unsupported:phase-14g:vehicle-charge-target-binding",
            "unsupported:phase-14g:crushing-impact",
        ),
        "epic-challenge": (
            "unsupported:phase-14g:character-model-fight-binding",
            "unsupported:phase-14g:epic-challenge",
        ),
        "heroic-intervention": (
            "unsupported:phase-14g:heroic-intervention-charge-unit",
            "unsupported:phase-14g:heroic-intervention",
        ),
    }
