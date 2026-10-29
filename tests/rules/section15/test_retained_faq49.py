"""FAQ49: a retained native model can receive the unit-targeted Core Stratagem.

Fight On Death permission is explicitly constructed at its established owner.
The supported Lord's identity, base, weapon profiles and character keyword stay native.
"""

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section05_retention import retain, terminal_retention
from tests.support.section15_fixtures import binding, context, record, request
from warhammer40k_core.core.weapon_profiles import WeaponKeyword
from warhammer40k_core.engine.command_points import CommandPointSourceKind
from warhammer40k_core.engine.decision_request import PARAMETERIZED_DECISION_OPTION_ID
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.fight_resolution import _epic_challenge_profile_if_applicable
from warhammer40k_core.engine.stratagems import (
    StratagemTargetProposal,
    apply_stratagem_target_proposal,
    invalid_stratagem_target_proposal_status,
    request_stratagem_target_proposal,
)
from warhammer40k_core.engine.timing_windows import TimingTriggerKind


def test_retained_native_character_receives_precision_before_its_removal(
    section15_definitions: Section02Definitions,
) -> None:
    d = section15_definitions
    state, target, decisions, retention = terminal_retention(d, melee=True, distance=2)
    retain(state, decisions, retention)
    mid = target.own_model_ids()[0]
    from warhammer40k_core.engine.damage_allocation import model_by_id

    assert not model_by_id(state=state, model_instance_id=mid).is_alive
    state.gain_command_points(
        player_id="opponent",
        amount=1,
        source_id="constructed:s15:cp",
        source_kind=CommandPointSourceKind.OTHER,
    )
    ctx = context(
        state,
        TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_SELECTED_TO_FIGHT,
        {"selected_unit_instance_id": target.unit_instance_id},
        player="opponent",
    )
    proposal = StratagemTargetProposal.for_request(
        context=ctx, catalog_record=record("epic-challenge")
    )
    req = request(
        request_stratagem_target_proposal(
            state=state, decisions=decisions, proposal_request=proposal
        )
    )
    bound = proposal.with_binding(
        binding(target.unit_instance_id, "opponent"),
        effect_selection={"character_model_instance_id": mid},
    )
    result = DecisionResult(
        "s15:retained",
        req.request_id,
        req.decision_type,
        req.actor_id,
        PARAMETERIZED_DECISION_OPTION_ID,
        validate_json_value({"proposal": bound.to_payload()}),
    )
    assert (
        invalid_stratagem_target_proposal_status(
            state=state,
            request=req,
            result=result,
            ruleset_descriptor=state.runtime_ruleset_descriptor(),
            army_catalog=d.package.army_catalog,
            decisions=decisions,
        )
        is None
    )
    decisions.submit_result(result)
    use = apply_stratagem_target_proposal(
        state=state,
        result=result,
        decisions=decisions,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        army_catalog=d.package.army_catalog,
    )
    assert use.targeted_unit_instance_ids == (target.unit_instance_id,)
    changed = _epic_challenge_profile_if_applicable(
        state=state,
        unit_instance_id=target.unit_instance_id,
        attacker_model_instance_id=mid,
        profile=d.weapon("000004078:close-combat-weapon"),
    )
    assert WeaponKeyword.PRECISION in changed.keywords
    assert state.command_point_total("opponent") == 0
