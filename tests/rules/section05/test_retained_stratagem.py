"""Core Epic Challenge accepted at its proposal boundary on a retained native Lord.

The timing context is explicit; this does not certify natural phase discovery or D12.
"""

import pytest

from tests.support.section02_fixtures import LORD_EXULTANT, Section02Definitions
from tests.support.section05_retention import retain, terminal_retention
from tests.support.section05_sequence import native_sequence
from warhammer40k_core.core.weapon_profiles import WeaponKeyword
from warhammer40k_core.engine.command_points import CommandPointSourceKind
from warhammer40k_core.engine.decision_request import PARAMETERIZED_DECISION_OPTION_ID
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.fight_resolution import (
    _epic_challenge_profile_if_applicable,
)
from warhammer40k_core.engine.stratagem_catalog import (
    eleventh_edition_core_stratagem_index,
)
from warhammer40k_core.engine.stratagems import (
    CORE_EPIC_CHALLENGE_HANDLER_ID,
    StratagemEligibilityContext,
    StratagemTargetBinding,
    apply_stratagem_target_proposal,
    invalid_stratagem_target_proposal_status,
    request_stratagem_target_proposal,
    stratagem_target_proposal_from_index,
)
from warhammer40k_core.engine.timing_windows import TimingTriggerKind


@pytest.mark.parametrize("retained", [False, True])
def test_faq49_retained_model_receives_unit_targeted_stratagem(
    section05_definitions: Section02Definitions, retained: bool
) -> None:
    d = section05_definitions
    if retained:
        state, target, decisions, retention_request = terminal_retention(d, melee=True, distance=2)
        retain(state, decisions, retention_request)
    else:
        from warhammer40k_core.engine.decision_controller import DecisionController

        state, target, _ = native_sequence(d, melee=True, distance=2)
        decisions = DecisionController()
    mid = target.own_model_ids()[0]
    state.gain_command_points(
        player_id="opponent",
        amount=1,
        source_id="constructed:s05:cp",
        source_kind=CommandPointSourceKind.OTHER,
    )
    context = StratagemEligibilityContext.from_state(
        state=state,
        player_id="opponent",
        trigger_kind=TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_SELECTED_TO_FIGHT,
        timing_window_id="constructed:s05:selected-to-fight",
        trigger_payload={"selected_unit_instance_id": target.unit_instance_id},
    )
    proposal = stratagem_target_proposal_from_index(
        state=state,
        index=eleventh_edition_core_stratagem_index(),
        context=context,
        handler_id=CORE_EPIC_CHALLENGE_HANDLER_ID,
    )
    assert proposal is not None
    status = request_stratagem_target_proposal(
        state=state, decisions=decisions, proposal_request=proposal
    )
    request = status.decision_request
    assert request is not None
    assert request.actor_id == "opponent"
    bound = proposal.with_binding(
        StratagemTargetBinding(
            target_kind=proposal.target_spec.target_kind,
            target_player_id="opponent",
            target_unit_instance_id=target.unit_instance_id,
        ),
        effect_selection={"character_model_instance_id": mid},
    )
    result = DecisionResult(
        result_id="s05:epic",
        request_id=request.request_id,
        decision_type=request.decision_type,
        actor_id=request.actor_id,
        selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
        payload=validate_json_value({"proposal": bound.to_payload()}),
    )
    invalid = invalid_stratagem_target_proposal_status(
        state=state,
        request=request,
        result=result,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        army_catalog=d.package.army_catalog,
        decisions=decisions,
    )
    assert invalid is None
    decisions.submit_result(result)
    apply_stratagem_target_proposal(
        state=state,
        result=result,
        decisions=decisions,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        army_catalog=d.package.army_catalog,
    )
    profile = d.weapon(f"{LORD_EXULTANT}:close-combat-weapon")
    assert WeaponKeyword.PRECISION not in profile.keywords
    changed = _epic_challenge_profile_if_applicable(
        state=state,
        unit_instance_id=target.unit_instance_id,
        attacker_model_instance_id=mid,
        profile=profile,
    )
    assert WeaponKeyword.PRECISION in changed.keywords
    assert state.command_point_total("opponent") == 0
