"""Canonical unit grant exercising the conditional Action FAQ, not faction support."""

from __future__ import annotations

from dataclasses import replace
from typing import cast

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.datasheet import (
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
    CatalogJsonObject,
    DatasheetAbilityDescriptor,
)
from warhammer40k_core.engine.mission_action_battle_shock import (
    ACTION_BATTLE_SHOCK_PERMISSION,
    ACTION_BATTLE_SHOCK_PERMISSION_SOURCE_ID,
)
from warhammer40k_core.rules.parsed_tokens import TextSpan
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleDuration,
    RuleDurationKind,
    RuleEffectKind,
    RuleEffectSpec,
    RuleIR,
    RuleTargetKind,
    RuleTargetSpec,
    parameters_from_pairs,
)


def action_permission_catalog(catalog: ArmyCatalog) -> ArmyCatalog:
    text = "This unit can start an action when it is battle-shocked."
    span = TextSpan(text=text, start=0, end=len(text))
    source = ACTION_BATTLE_SHOCK_PERMISSION_SOURCE_ID
    rule = RuleIR(
        rule_id="test:order110:explicit-permission",
        source_id=source,
        normalized_text=text,
        parser_version="test:order110:conditional-faq-premise",
        clauses=(
            RuleClause(
                clause_id="test:order110:permission",
                source_span=span,
                target=RuleTargetSpec(kind=RuleTargetKind.THIS_UNIT, source_span=span),
                duration=RuleDuration(kind=RuleDurationKind.PERMANENT, source_span=span),
                effects=(
                    RuleEffectSpec(
                        kind=RuleEffectKind.GRANT_ABILITY,
                        source_span=span,
                        parameters=parameters_from_pairs(
                            (("ability", ACTION_BATTLE_SHOCK_PERMISSION),)
                        ),
                    ),
                ),
            ),
        ),
    )
    descriptor = DatasheetAbilityDescriptor(
        ability_id="test:order110:permission",
        name="Explicit Action permission",
        source_id=source,
        support=CatalogAbilitySupport.GENERIC_RULE_IR,
        source_kind=CatalogAbilitySourceKind.DATASHEET,
        effect_description=text,
        rule_ir_payload=cast(CatalogJsonObject, rule.to_payload()),
    )
    return replace(
        catalog,
        datasheets=tuple(
            replace(sheet, abilities=(*sheet.abilities, descriptor)) for sheet in catalog.datasheets
        ),
    )


def action_walker_catalog(catalog: ArmyCatalog, *, permission: bool) -> ArmyCatalog:
    source = action_permission_catalog(catalog) if permission else catalog
    return replace(
        source,
        datasheets=tuple(
            replace(
                sheet,
                keywords=replace(
                    sheet.keywords,
                    keywords=(
                        "VEHICLE",
                        "WALKER",
                        "SUPER_HEAVY_WALKER",
                    ),
                ),
            )
            for sheet in source.datasheets
        ),
    )


def shocked_action_opportunity_session(
    *, permission: bool, game_id: str = "order110-walker-0"
) -> tuple[LocalGameSession, str]:
    from tests.action_movement_interruption_helpers import action_opportunity_session
    from warhammer40k_core.engine.event_log import validate_json_value
    from warhammer40k_core.engine.movement_proposals import (
        MovementProposalPayload,
        MovementProposalRequest,
    )
    from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
    from warhammer40k_core.geometry.pathing import PathWitness

    session, unit_id = action_opportunity_session(
        catalog_transform=lambda catalog: action_walker_catalog(catalog, permission=permission),
        starting_phase=BattlePhase.MOVEMENT,
        game_id=game_id,
    )
    request = session.advance_until_decision_or_terminal().decision_request
    assert request is not None
    request = session.submit_option(
        request_id=request.request_id, option_id=unit_id, result_id="order110:select-walker"
    ).decision_request
    assert request is not None
    request = session.submit_option(
        request_id=request.request_id,
        option_id="normal_move:move_keywords",
        result_id="order110:select-move",
    ).decision_request
    assert request is not None
    proposal = MovementProposalRequest.from_decision_request_payload(request.payload)
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    placement = state.battlefield_state.unit_placement_by_id(unit_id)
    witness = PathWitness.for_paths(
        tuple(
            (model.model_instance_id, (model.pose, model.pose))
            for model in placement.model_placements
        )
    )
    submission = MovementProposalPayload(
        proposal_request_id=request.request_id,
        proposal_kind=proposal.proposal_kind,
        unit_instance_id=unit_id,
        movement_phase_action="normal_move",
        movement_mode="normal",
        fall_back_mode=None,
        witness=witness,
    )
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="order110:walker-path",
        payload=validate_json_value(submission.to_payload()),
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status
    rolls = [
        e.payload
        for e in session.lifecycle.decision_controller.event_log.records
        if e.event_type == "move_keyword_roll_resolved"
    ]
    assert state.battle_shocked_unit_ids, rolls
    from warhammer40k_core.engine.stratagems_requests import stratagem_decline_payload

    request = status.decision_request
    assert request is not None
    assert request.decision_type == "submit_stratagem_target_proposal"
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="order110:decline-overwatch",
        payload=stratagem_decline_payload(),
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status
    assert state.current_battle_phase is BattlePhase.SHOOTING
    return session, unit_id


def resolve_action_battle_shock_test(session: LocalGameSession, unit_id: str) -> None:
    """Exercise the actual failed-test owner with a canonical domain test request."""
    from warhammer40k_core.engine.battle_shock import (
        BattleShockResult,
        BattleShockTestReason,
        BattleShockTestRequest,
    )
    from warhammer40k_core.engine.battle_shock_resolution import (
        BattleShockPassedStatePolicy,
        record_precomputed_battle_shock_result_events,
    )
    from warhammer40k_core.engine.dice import DiceRollManager
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
    from warhammer40k_core.engine.unit_state import BelowHalfStrengthContext

    state = session.lifecycle.state
    assert state is not None
    phase = state.current_battle_phase
    assert phase is not None
    view = rules_unit_view_by_id(state=state, unit_instance_id=unit_id)
    request = BattleShockTestRequest.for_unit(
        request_id="order110:test-producer",
        game_id=state.game_id,
        battle_round=state.battle_round,
        player_id=view.owner_player_id,
        unit_instance_id=unit_id,
        reason=BattleShockTestReason.FORCED_BY_ARMY_RULE,
        leadership_target=6,
        below_half_strength_context=BelowHalfStrengthContext.from_rules_unit(
            rules_unit=view,
            starting_strength=state.starting_strength_record_for_unit(unit_id),
            current_model_ids=tuple(m.model_instance_id for m in view.alive_models()),
        ),
    )
    result = BattleShockResult.from_roll_state(
        result_id="order110:test-producer:result",
        request=request,
        roll_state=DiceRollManager(state.game_id).roll_fixed(request.spec, [1, 1]),
    )
    record_precomputed_battle_shock_result_events(
        state=state,
        decisions=session.lifecycle.decision_controller,
        result=result,
        phase=phase,
        auto_passed=False,
        phase_start_battle_shocked_unit_ids=(),
        passed_state_policy=BattleShockPassedStatePolicy.PRESERVE,
        base_payload={
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": state.active_player_id,
            "phase": phase.value,
        },
        resolved_event_types=("battle_shock_test_resolved",),
        modifier_applications=(),
    )
