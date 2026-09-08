"""Exercise live target preflight on authenticated casualty checkpoints."""

from dataclasses import replace

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine import stratagems_generic_metadata as generic_metadata
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.rule_execution import RuleExecutionContext
from warhammer40k_core.engine.rule_target_resolution import effect_clause_target_unavailable_reason
from warhammer40k_core.engine.stratagem_catalog import (
    eleventh_edition_core_stratagem_catalog_records,
)
from warhammer40k_core.engine.stratagems import (
    StratagemEligibilityContext,
    StratagemRestrictionPolicy,
    StratagemTargetBinding,
    StratagemTargetKind,
    StratagemTargetProposal,
    StratagemTargetSpec,
    StratagemTimingDescriptor,
    create_stratagem_target_proposal_decision_request,
    invalid_stratagem_target_proposal_status,
)
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.rules.parsed_tokens import TextSpan
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleEffectKind,
    RuleEffectSpec,
    RuleParameter,
    RuleTargetKind,
    RuleTargetSpec,
)


def assert_keyword_target_eligibility(session: LocalGameSession, *, present: bool) -> None:
    # Request allocation belongs to a separate restored lifecycle, leaving the
    # casualty/replay scenario's decision sequence unchanged.
    checkpoint = session.lifecycle.to_payload()
    probe = GameLifecycle.from_payload(checkpoint)
    state = probe.state
    assert state is not None
    context = RuleExecutionContext(
        game_id=state.game_id,
        player_id="player-b",
        battle_round=state.battle_round,
        phase=state.current_battle_phase,
        active_player_id=state.active_player_id,
        target_unit_instance_ids=("army-beta:enemy",),
        state=state,
    )
    for keyword in ("PSYKER", "CORE MARINES"):
        span = TextSpan(start=0, end=len(keyword), text=keyword)
        clause = RuleClause(
            clause_id="order31-target-keyword",
            source_span=span,
            target=RuleTargetSpec(
                kind=RuleTargetKind.FRIENDLY_UNIT,
                source_span=span,
                parameters=(RuleParameter(key="required_keyword", value=keyword),),
            ),
            effects=(RuleEffectSpec(kind=RuleEffectKind.GRANT_ABILITY, source_span=span),),
        )
        assert effect_clause_target_unavailable_reason(clause=clause, context=context) == (
            None if present else "unit_missing_required_keyword"
        )
    base = eleventh_edition_core_stratagem_catalog_records()[0]
    stratagem_context = StratagemEligibilityContext.from_state(
        state=state,
        player_id="player-b",
        trigger_kind=TimingTriggerKind.DURING_PHASE,
    )
    cases = (
        (
            StratagemTargetSpec(
                target_kind=StratagemTargetKind.FRIENDLY_UNIT, required_keywords=("PSYKER",)
            ),
            "unit_missing_required_keyword",
            present,
        ),
        (
            StratagemTargetSpec(
                target_kind=StratagemTargetKind.FRIENDLY_UNIT,
                required_keywords_any=("PSYKER", "MONSTER"),
            ),
            "unit_missing_required_keyword",
            present,
        ),
        (
            StratagemTargetSpec(
                target_kind=StratagemTargetKind.FRIENDLY_UNIT,
                required_faction_keywords=("CORE MARINES",),
            ),
            "unit_missing_required_faction_keyword",
            present,
        ),
        (
            StratagemTargetSpec(
                target_kind=StratagemTargetKind.FRIENDLY_UNIT, excluded_keywords=("PSYKER",)
            ),
            "unit_has_excluded_keyword",
            not present,
        ),
        (
            StratagemTargetSpec(
                target_kind=StratagemTargetKind.FRIENDLY_UNIT,
                excluded_faction_keywords=("CORE MARINES",),
            ),
            "unit_has_excluded_faction_keyword",
            not present,
        ),
    )
    for index, (spec, reason, allowed) in enumerate(cases):
        record = replace(
            base,
            definition=replace(
                base.definition,
                stratagem_id=f"order31-target-policy-{index}",
                source_id=f"fixture:order31-target-policy-{index}",
                command_point_cost=0,
                handler_id="record_only",
                effect_payload=None,
                eligible_roll_types=(),
                timing=StratagemTimingDescriptor(
                    trigger_kind=TimingTriggerKind.DURING_PHASE, phase=state.current_battle_phase
                ),
                restriction_policy=StratagemRestrictionPolicy(
                    same_stratagem_per_phase=False, same_unit_target_per_phase=False
                ),
                target_spec=replace(
                    spec,
                    target_kind=StratagemTargetKind.FRIENDLY_UNIT,
                    enumerable=False,
                    target_policy_id="friendly_unit",
                ),
            ),
        )
        proposal = StratagemTargetProposal.for_request(
            context=stratagem_context, catalog_record=record
        )
        request = create_stratagem_target_proposal_decision_request(
            state=state, proposal_request=proposal
        )
        submitted = proposal.with_binding(
            StratagemTargetBinding(
                target_kind=StratagemTargetKind.FRIENDLY_UNIT,
                target_player_id="player-b",
                target_unit_instance_id="army-beta:enemy",
            )
        )
        result = DecisionResult(
            result_id=f"order31-policy-{index}",
            request_id=request.request_id,
            decision_type=request.decision_type,
            actor_id=request.actor_id,
            selected_option_id=request.options[0].option_id,
            payload=validate_json_value({"proposal": submitted.to_payload()}),
        )
        status = invalid_stratagem_target_proposal_status(
            state=state,
            request=request,
            result=result,
            ruleset_descriptor=probe.config.ruleset_descriptor,
            army_catalog=probe.config.army_catalog,
            decisions=probe.decision_controller,
        )
        if allowed:
            assert status is None, (index, status)
        else:
            assert status is not None
            assert isinstance(status.payload, dict)
            assert status.payload["invalid_reason"] == reason
    for target_id, companion_id, mapping in (
        ("army-beta:enemy", "army-beta:support", {"PSYKER": ["VEHICLE"]}),
        ("army-beta:support", "army-beta:enemy", {"VEHICLE": ["PSYKER"]}),
        ("army-beta:enemy", "army-beta:support", {"CORE MARINES": ["VEHICLE"]}),
        ("army-beta:support", "army-beta:enemy", {"VEHICLE": ["CORE MARINES"]}),
    ):
        definition = replace(
            base.definition,
            effect_payload=validate_json_value(
                {
                    generic_metadata.COMPANION_REQUIRED_KEYWORDS_BY_TARGET_KEYWORD_KEY: mapping,
                }
            ),
        )
        binding = StratagemTargetBinding(
            target_kind=StratagemTargetKind.FRIENDLY_UNIT,
            target_player_id="player-b",
            target_unit_instance_id=target_id,
        )
        selection = generic_metadata.companion_unit_effect_selection(companion_id)
        selections = generic_metadata.companion_effect_selections_for_binding(
            state=state,
            definition=definition,
            context=stratagem_context,
            target_binding=binding,
        )
        assert (selection in selections) is present
        assert generic_metadata.companion_selection_error(
            state=state,
            definition=definition,
            context=stratagem_context,
            target_binding=binding,
            effect_selection=selection,
        ) == (None if present else "companion_unit_keyword_mismatch")
    assert session.lifecycle.to_payload() == checkpoint
