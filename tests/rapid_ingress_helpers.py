"""Canonical reserve fixtures and facade submissions for the Order 35 matrix."""

from __future__ import annotations

from dataclasses import replace
from typing import cast

from tests.core_stratagem_helpers import _battle_lifecycle, _config, _reserve_placement
from tests.psychic_modifier_helpers import pending_request
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.datasheet import (
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
    CatalogJsonObject,
    DatasheetAbilityDescriptor,
)
from warhammer40k_core.engine.command_points import CommandPointSourceKind
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.movement_proposals import (
    MovementProposalRequest,
    PlacementProposalPayload,
)
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatus
from warhammer40k_core.engine.reserves import ReserveKind
from warhammer40k_core.engine.stratagems import (
    StratagemEligibilityContext,
    StratagemTargetBinding,
    StratagemTargetKind,
    StratagemTargetProposal,
    StratagemTargetProposalPayload,
)
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.objective_terminology import ObjectiveRuleScope
from warhammer40k_core.rules.rule_compiler import compile_rule_source_text
from warhammer40k_core.rules.source_data import RuleSourceText
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    datasheet_keyword_lexicon_2026_06_14 as keyword_lexicon,
)


def ingress_session(
    *,
    battle_round: int = 2,
    reacting_player: str = "player-b",
    inventory: tuple[str, ...] = ("INFANTRY",),
    automatic_discount: bool = False,
) -> LocalGameSession:
    # Both player identities react using identical armies and authoritative turn order.
    active = "player-a" if reacting_player == "player-b" else "player-b"
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    sheet = catalog.datasheet_by_id("core-intercessor-like-infantry")
    if automatic_discount:
        source = RuleSourceText.from_raw(
            source_id="test:order35:automatic-discount",
            raw_text=(
                "Each time you target this model's unit with a Stratagem, reduce the CP cost "
                "of that use of that Stratagem by 1CP."
            ),
            objective_scope=ObjectiveRuleScope.CORE_RULES,
        )
        rule_ir = compile_rule_source_text(
            source,
            source_keyword_sequence_parts=keyword_lexicon.canonical_datasheet_keyword_sequence_parts(),
        ).rule_ir
        sheet = replace(
            sheet,
            abilities=(
                *sheet.abilities,
                DatasheetAbilityDescriptor(
                    ability_id="order35-automatic-discount",
                    name="Automatic discount fixture",
                    source_id=source.source_id,
                    support=CatalogAbilitySupport.GENERIC_RULE_IR,
                    source_kind=CatalogAbilitySourceKind.DATASHEET,
                    effect_description=source.raw_text,
                    rule_ir_payload=cast(CatalogJsonObject, rule_ir.to_payload()),
                ),
            ),
        )
    variants = tuple(
        replace(
            sheet,
            datasheet_id=f"order35-{k.lower()}",
            keywords=replace(sheet.keywords, keywords=(k,)),
        )
        for k in sorted(set(inventory))
    )
    catalog = replace(
        catalog,
        datasheets=(*catalog.datasheets, *variants),
        detachments=tuple(
            replace(
                d, unit_datasheet_ids=(*d.unit_datasheet_ids, *(v.datasheet_id for v in variants))
            )
            for d in catalog.detachments
        ),
    )
    config = _config(
        catalog=catalog,
        beta_unit_selection_ids=tuple(f"reserve-{i}" for i in range(max(1, len(inventory)))),
        beta_datasheet_ids=tuple(f"order35-{k.lower()}" for k in inventory) if inventory else None,
    )
    if reacting_player == "player-a":
        config = replace(
            config,
            army_muster_requests=tuple(
                replace(
                    r,
                    player_id="player-a" if r.player_id == "player-b" else "player-b",
                    force_disposition_id="take-and-hold"
                    if r.player_id == "player-b"
                    else "purge-the-foe",
                )
                for r in config.army_muster_requests
            ),
            turn_order=("player-b", "player-a"),
        )
    lifecycle = _battle_lifecycle(
        config,
        battle_round=battle_round,
        active_player_id=active,
        reserve_units=tuple(
            (reacting_player, f"army-beta:reserve-{i}") for i in range(len(inventory))
        ),
        reserve_kind=ReserveKind.STRATEGIC_RESERVES,
        clear_terrain=True,
    )
    state = lifecycle.state
    assert state is not None
    state.gain_command_points(
        player_id=reacting_player,
        amount=3,
        source_id="order35:fixture",
        source_kind=CommandPointSourceKind.OTHER,
    )
    return LocalGameSession(lifecycle=lifecycle)


def ingress_context(session: LocalGameSession) -> StratagemEligibilityContext:
    state = session.lifecycle.state
    assert state is not None
    return StratagemEligibilityContext(
        game_id=state.game_id,
        player_id=next(p for p in state.player_ids if p != state.active_player_id),
        battle_round=state.battle_round,
        phase=BattlePhase.MOVEMENT,
        active_player_id=state.active_player_id,
        timing_window_id="order35:end-movement",
        trigger_kind=TimingTriggerKind.END_PHASE,
    )


def reach_ingress_window(session: LocalGameSession) -> DecisionRequest:
    for i in range(80):
        request = pending_request(session)
        if request.decision_type == "submit_stratagem_target_proposal":
            return request
        if request.decision_type == "select_movement_unit":
            option = request.options[0].option_id
        elif request.decision_type == "select_movement_action":
            option = "remain_stationary"
        else:
            return request
        session.submit_option(
            request_id=request.request_id, result_id=f"order35:move:{i}", option_id=option
        )
    raise AssertionError("Movement window did not close")


def submit_ingress_target(
    session: LocalGameSession, request: DecisionRequest, *, target: str = "army-beta:reserve-0"
) -> LifecycleStatus:
    assert isinstance(request.payload, dict)
    proposal = StratagemTargetProposal.from_payload(
        cast(StratagemTargetProposalPayload, request.payload["proposal_request"])
    )
    return session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="order35:target",
        payload=validate_json_value(
            {
                "proposal": proposal.with_binding(
                    StratagemTargetBinding(
                        target_kind=StratagemTargetKind.FRIENDLY_UNIT,
                        target_player_id=request.actor_id,
                        target_unit_instance_id=target,
                    )
                ).to_payload()
            }
        ),
    )


def ingress_placement(
    session: LocalGameSession, request: DecisionRequest
) -> PlacementProposalPayload:
    proposal = MovementProposalRequest.from_decision_request_payload(request.payload)
    state = session.lifecycle.state
    assert state is not None
    assert request.actor_id is not None
    army = state.army_definition_for_player(request.actor_id)
    assert army is not None
    unit = army.unit_by_id(proposal.unit_instance_id)
    return PlacementProposalPayload(
        proposal_request_id=request.request_id,
        proposal_kind=proposal.proposal_kind,
        unit_instance_id=unit.unit_instance_id,
        placement_kind=proposal.placement_kinds[0],
        attempted_placement=_reserve_placement(
            army=army,
            reserve_unit=unit,
            poses=tuple(
                Pose.at(24 + i * 2, 40 if request.actor_id == "player-b" else 4)
                for i, _ in enumerate(unit.own_models)
            ),
        ),
    )
