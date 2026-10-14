"""Real melee activation and the original strict generic weapon-dispatch guards."""

from typing import cast

import pytest
from tests.epic_challenge_helpers import epic_checkpoint
from tests.psychic_modifier_helpers import submit_fixture_request
from tests.s25_characteristic_melee_projection_helpers import projection_melee_request

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.engine.decision_request import DecisionError
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.fight_resolution import MeleeDeclarationProposalRequest
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatusKind
from warhammer40k_core.engine.rule_ir_weapon_modifiers import rule_ir_modified_weapon_profile


@pytest.mark.parametrize("player", ["player-a", "player-b"])
@pytest.mark.parametrize(
    "characteristic",
    [Characteristic.WEAPON_SKILL, Characteristic.BALLISTIC_SKILL, Characteristic.RANGE],
)
def test_admitted_melee_root_uses_actual_skill_and_range_gates(
    player: str, characteristic: Characteristic
) -> None:
    session, request = projection_melee_request(player=player, characteristic=characteristic)
    proposal = MeleeDeclarationProposalRequest.from_decision_request(request)
    weapons = [
        cast(dict[str, JsonValue], w)
        for w in proposal.available_weapons
        if cast(dict[str, JsonValue], w)["wargear_id"] == "core-bolt-rifle"
    ]
    assert len(weapons) == 5
    payload: dict[str, JsonValue] = {
        "proposal_request_id": proposal.request_id,
        "proposal_kind": proposal.proposal_kind,
        "player_id": proposal.actor_id,
        "battle_round": proposal.battle_round,
        "unit_instance_id": proposal.unit_instance_id,
        "source_decision_request_id": proposal.source_decision_request_id,
        "source_decision_result_id": proposal.source_decision_result_id,
        "declarations": [
            {
                "attacker_model_instance_id": weapon["model_instance_id"],
                "weapon_instance_id": weapon["weapon_instance_id"],
                "wargear_id": weapon["wargear_id"],
                "weapon_profile_id": weapon["weapon_profile_id"],
                "target_allocations": [
                    {
                        "target_unit_instance_id": cast(
                            list[str], weapon["engaged_target_unit_instance_ids"]
                        )[0]
                    }
                ],
            }
            for weapon in weapons
        ],
    }
    status = session.submit_parameterized_payload(
        request_id=request.request_id, result_id="s25-projection-melee:declaration", payload=payload
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
    state = session.lifecycle.state
    assert state is not None
    assert state.fight_phase_state is not None
    sequence = state.fight_phase_state.attack_sequence
    assert sequence is not None
    assert len(sequence.attack_pools) == 5
    pools = sequence.attack_pools
    used = characteristic is Characteristic.WEAPON_SKILL
    if used:
        assert sequence.current_gathered_group is None
        assert isinstance(pools[0].weapon_profile.skill, CharacteristicValue)
        assert isinstance(pools[1].weapon_profile.skill, CharacteristicValue)
        assert pools[0].weapon_profile.skill.final == pools[1].weapon_profile.skill.final + 1
        assert pools[0].weapon_profile.to_payload() != pools[1].weapon_profile.to_payload()
    else:
        group = sequence.current_gathered_group
        assert group is not None
        assert group.pool_indices == (0, 1, 2, 3, 4)
        assert group.total_attacks == 10
        assert all(
            pool.weapon_profile.to_payload() == pools[0].weapon_profile.to_payload()
            for pool in pools
        )
        assert len({s.rules_json for s in group.native_snapshots}) == 1
        assert len({s.raw_signature_json for s in group.native_snapshots}) == 5
    events = session.lifecycle.decision_controller.event_log.records
    activations = [
        e.payload
        for e in events
        if e.event_type == "catalog_any_phase_once_per_battle_ability_activated"
        and isinstance(e.payload, dict)
    ]
    assert len(activations) == 1
    assert activations[0]["source_model_instance_id"] == pools[0].attacker_model_instance_id
    pending = session.advance_until_decision_or_terminal().decision_request
    assert pending is not None
    before = session.to_persistence_payload()
    with pytest.raises(DecisionError, match="finite action space"):
        session.submit_option(
            request_id=pending.request_id,
            option_id="s25-projection-melee:invalid",
            result_id="s25-projection-melee:invalid",
        )
    assert session.to_persistence_payload() == before
    epic_checkpoint(session)
    for _ in range(160):
        if any(
            e.event_type == "attack_sequence_completed"
            for e in session.lifecycle.decision_controller.event_log.records
        ):
            break
        pending = session.advance_until_decision_or_terminal().decision_request
        if any(
            e.event_type == "attack_sequence_completed"
            for e in session.lifecycle.decision_controller.event_log.records
        ):
            break
        assert pending is not None
        submit_fixture_request(session, pending)
    else:
        raise AssertionError("Projection melee attack did not complete natively.")
    epic_checkpoint(session)
    events = session.lifecycle.decision_controller.event_log.records
    stages = {
        name: [
            i
            for i, e in enumerate(events)
            if e.event_type == "dice_rolled"
            and isinstance(e.payload, dict)
            and cast(dict[str, JsonValue], e.payload["spec"]).get("roll_type")
            == "attack_sequence." + name
        ]
        for name in ("hit", "wound")
    }
    assert len(stages["hit"]) == 10
    assert stages["wound"]
    if not used:
        assert max(stages["hit"]) < min(stages["wound"])


@pytest.mark.parametrize("melee", [False, True])
@pytest.mark.parametrize("invalid", ["delta", "source", "characteristic"])
def test_original_dispatch_validation_precedes_known_profile_noop(
    melee: bool, invalid: str
) -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    weapon = next(
        w
        for w in catalog.wargear
        if w.wargear_id == ("core-leader-blade" if melee else "core-bolt-rifle")
    ).weapon_profiles[0]
    parameters: dict[str, object] = {
        "characteristic": "range" if melee else "weapon_skill",
        "delta": 1,
    }
    assert (
        rule_ir_modified_weapon_profile(
            parameters=parameters,
            profile=weapon,
            source_id="analytical:s25-noop",
            modifier_id="s25-noop",
        )
        == weapon
    )
    if invalid == "delta":
        parameters["delta"] = True
        error = "must be an integer"
    elif invalid == "characteristic":
        parameters["characteristic"] = "unknown"
        error = "characteristic is invalid"
    else:
        error = "source_id must be non-empty"
    with pytest.raises(GameLifecycleError, match=error):
        rule_ir_modified_weapon_profile(
            parameters=parameters,
            profile=weapon,
            source_id="" if invalid == "source" else "analytical:s25-noop",
            modifier_id="s25-noop",
        )
    with pytest.raises(GameLifecycleError, match="characteristic is unsupported"):
        rule_ir_modified_weapon_profile(
            parameters={"characteristic": "leadership", "delta": 1},
            profile=weapon,
            source_id="analytical:s25-unsupported-weapon",
            modifier_id="s25-unsupported-weapon",
        )
