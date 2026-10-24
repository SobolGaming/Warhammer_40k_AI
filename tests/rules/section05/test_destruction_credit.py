"""Actual attack/rule attribution and the scoring evidence gate for other causes."""

from dataclasses import replace

import pytest

from tests.generic_modifier_helpers import generic_effect
from tests.support.section02_fixtures import Section02Definitions
from tests.support.section05_fixtures import replace_unit
from tests.support.section05_sequence import (
    fixed_sequence_dice,
    native_sequence,
    payloads,
    resolve,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.destruction_provenance import (
    DestructionSourceKind,
    ModelDestructionAttribution,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.primary_scoring_conditions import (
    PrimaryUnitDestructionEvidence,
)
from warhammer40k_core.engine.rule_model_destruction import (
    destroy_model_with_rule_reactions,
)


def test_native_attack_credits_actual_attacking_player_and_model(
    section05_definitions: Section02Definitions,
) -> None:
    state, target, sequence = native_sequence(section05_definitions)
    target = replace(target, own_models=(replace(target.own_models[0], wounds_remaining=1),))
    replace_unit(state, target)
    decisions, remaining, status = resolve(
        state, sequence, fixed_sequence_dice(sequence, target, (6,), (6,), (1,))
    )
    assert status is None
    assert remaining is None
    attribution = ModelDestructionAttribution.from_model_destroyed_payload(
        payloads(decisions, "model_destroyed")[0]
    )
    assert attribution.destroying_player_id == "owner"
    assert attribution.attacking_unit_instance_id == sequence.attacking_unit_instance_id
    assert (
        attribution.attacking_model_instance_id
        == sequence.attack_pools[0].attacker_model_instance_id
    )
    assert (
        attribution.destruction_provenance.destruction_source_kind is DestructionSourceKind.ATTACK
    )


@pytest.mark.parametrize("destroyer", ["owner", "opponent"])
def test_player_rule_credits_its_owner_not_other_player(
    section05_definitions: Section02Definitions, destroyer: str
) -> None:
    state, target, _ = native_sequence(section05_definitions)
    state.record_persisting_effect(
        generic_effect(
            effect_id="constructed:s05:rule-credit",
            owner_player_id=destroyer,
            target_unit_instance_ids=(target.unit_instance_id,),
            target_kind="selected_unit",
            effect_kind="set_contextual_status",
            parameters={"status": "s05_destruction_liability"},
        )
    )
    decisions = DecisionController()
    outcome = destroy_model_with_rule_reactions(
        state=state,
        decisions=decisions,
        model_instance_id=target.own_model_ids()[0],
        rules_unit_instance_id=target.unit_instance_id,
        destroying_player_id=destroyer,
        source_rule_id="constructed:s05:rule-credit",
        source_effect_ids=("constructed:s05:rule-credit",),
        source_phase=BattlePhase.SHOOTING,
        source_step="s05:rule",
        source_result_id="s05:rule-credit",
        completion_event_type="section05_rule_completed",
        completion_event_payload={},
    )
    assert outcome.status is None
    attribution = ModelDestructionAttribution.from_model_destroyed_payload(
        payloads(decisions, "model_destroyed")[0]
    )
    assert attribution.destroying_player_id == destroyer
    assert attribution.attacking_unit_instance_id is None
    assert (
        attribution.destruction_provenance.destruction_source_kind is DestructionSourceKind.ABILITY
    )
    assert (attribution.destroying_player_id == "owner") is (destroyer == "owner")


def test_unattributed_destruction_cannot_claim_player_kill_credit() -> None:
    # Constructed evidence at the actual scoring input validator; no mission startup needed.
    evidence = PrimaryUnitDestructionEvidence(
        destruction_id="constructed:s05:unattributed",
        battle_round=1,
        active_player_id="owner",
        destroying_player_id=None,
        destroyed_player_id="opponent",
        destroyed_unit_instance_id="enemy:target",
        destruction_attribution=None,
        source_rules_unit_objective_proximity_witness=None,
        started_turn_terrain_feature_ids=(),
        started_turn_objective_marker_ids=(),
    )
    assert evidence.destroying_player_id is None
    with pytest.raises(GameLifecycleError, match=r"Unattributed.*cannot identify a destroyer"):
        replace(evidence, destroying_player_id="owner")
