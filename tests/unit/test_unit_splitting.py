from __future__ import annotations

import json
from dataclasses import replace
from typing import cast

import pytest
from tests.deployment_submission_helpers import deployment_placement_payload_for_request
from tests.movement_submission_helpers import straight_line_witness_for_unit
from tests.phase11c_command_phase_helpers import (
    default_unit_selection,
    mustered_armies,
    phase11c_config,
    unit_selection,
)

from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.datasheet import (
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
    CatalogJsonObject,
    DatasheetAbilityDescriptor,
)
from warhammer40k_core.core.detachment import EnhancementDefinition
from warhammer40k_core.core.ruleset_descriptor import MovementMode
from warhammer40k_core.core.weapon_profiles import WeaponKeyword
from warhammer40k_core.engine.army_mustering import ArmyDefinition, EnhancementAssignment
from warhammer40k_core.engine.attached_unit_reconciliation import (
    validate_attached_rules_unit_identity_after_destruction,
)
from warhammer40k_core.engine.catalog_conditional_leader_queries import (
    CONDITIONAL_LEADER_ABILITY_DESCRIPTOR_ID,
    conditional_leading_source_unit_applies,
    conditional_not_leading_source_applies,
)
from warhammer40k_core.engine.catalog_rule_consumption import (
    catalog_rule_ir_consumers_for_rule,
    catalog_rule_ir_hook_ids_for_rule,
)
from warhammer40k_core.engine.damage_allocation import DamageKind, apply_damage_to_model
from warhammer40k_core.engine.deadly_demise_modifiers import deadly_demise_modifier_for_model
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.effects import (
    GENERIC_RULE_EFFECT_KIND,
    EffectExpiration,
    EffectExpirationKind,
    PersistingEffect,
)
from warhammer40k_core.engine.enhancement_bearers import (
    current_enhancement_bearer,
    enhancement_bearer_unit,
    runtime_assignment_for_current_bearer,
)
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentBundle
from warhammer40k_core.engine.fights_first import FightsFirstRegistry
from warhammer40k_core.engine.game_state import GameConfig
from warhammer40k_core.engine.generic_rule_attack_hooks import (
    generic_rule_hit_roll_modifier,
    generic_rule_modified_unit_characteristic,
)
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.list_validation import AttachmentDeclaration
from warhammer40k_core.engine.movement_proposals import (
    MovementProposalPayload,
    MovementProposalRequest,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatusKind,
)
from warhammer40k_core.engine.phases.movement import SELECT_MOVEMENT_UNIT_DECISION_TYPE
from warhammer40k_core.engine.rules_units import rules_unit_views_from_armies
from warhammer40k_core.engine.runtime_modifiers import (
    HitRollModifierContext,
    UnitCharacteristicModifierContext,
    WeaponProfileModifierContext,
)
from warhammer40k_core.engine.unit_resource_state import (
    initialize_unit_resource,
    unit_resource_ledger_for_unit,
)
from warhammer40k_core.engine.unit_split_decisions import SELECT_UNIT_SPLIT_MEMBERSHIP_DECISION_TYPE
from warhammer40k_core.engine.unit_split_permissions import (
    UNIT_SPLIT_CONSUMER_ID,
    unit_split_permissions,
)
from warhammer40k_core.engine.unit_splitting import build_split_army
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.objective_terminology import ObjectiveRuleScope
from warhammer40k_core.rules.rule_compiler import compile_rule_source_text
from warhammer40k_core.rules.rule_ir import RuleIR, RuleIRPayload, RuleParameter
from warhammer40k_core.rules.source_data import RuleSourceText
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    datasheet_keyword_lexicon_2026_06_14 as keyword_source,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_blood_legion_ir_support_2026_27 as blood_legion_ir,
)


def _split_config(base: GameConfig | None = None) -> GameConfig:
    # Real source shape: Tactical Squad Combat Squads, observed at
    # https://www.40k.app/factions/space-marines/units/tactical-squad on 2026-09-06.
    # Canonical engine fixtures exercise the rule without claiming faction support.
    source = "test-source:tactical-squad:combat-squads"
    text = (
        "At the start of the Declare Battle Formations step, before any units have been set up, "
        "this unit can be split into two units, each containing five models."
    )
    rule = compile_rule_source_text(
        RuleSourceText.from_raw(
            source_id=source, raw_text=text, objective_scope=ObjectiveRuleScope.NON_CORE_RULES
        ),
        source_keyword_sequence_parts=keyword_source.canonical_datasheet_keyword_sequence_parts(),
    ).rule_ir
    ability = DatasheetAbilityDescriptor(
        ability_id="test-combat-squads",
        name="Combat Squads",
        source_id=source,
        support=CatalogAbilitySupport.GENERIC_RULE_IR,
        source_kind=CatalogAbilitySourceKind.DATASHEET,
        effect_description=text,
        rule_ir_payload=cast(CatalogJsonObject, rule.to_payload()),
    )
    config = phase11c_config() if base is None else base
    catalog = replace(
        config.army_catalog,
        datasheets=tuple(
            replace(d, abilities=(*d.abilities, ability))
            if d.datasheet_id == "core-intercessor-like-infantry"
            else d
            for d in config.army_catalog.datasheets
        ),
    )
    return replace(config, army_catalog=catalog)


def _submit_first(session: LocalGameSession) -> None:
    request = session.lifecycle.decision_controller.queue.peek_next()
    assert request is not None
    assert request.actor_id is not None
    session.submit_option(
        request_id=request.request_id,
        option_id=request.options[0].option_id,
        result_id=f"result:{request.request_id}",
    )


@pytest.mark.parametrize("attached", [False, True])
def test_split_choices_use_session_and_checkpoint_round_trip(attached: bool) -> None:
    session = LocalGameSession()
    config = (
        phase11c_config()
        if not attached
        else phase11c_config(
            player_a_units=(
                default_unit_selection("bodyguard"),
                unit_selection(
                    unit_selection_id="leader",
                    datasheet_id="core-character-leader",
                    model_profile_id="core-character-leader",
                    model_count=1,
                ),
            ),
            player_a_attachment_declarations=(
                AttachmentDeclaration(
                    source_unit_selection_id="leader",
                    bodyguard_unit_selection_id="bodyguard",
                ),
            ),
        )
    )
    session.start(_split_config(config))
    status = session.advance_until_decision_or_terminal()
    while (
        status.decision_request is not None
        and status.decision_request.decision_type != SELECT_UNIT_SPLIT_MEMBERSHIP_DECISION_TYPE
    ):
        _submit_first(session)
        status = session.advance_until_decision_or_terminal()
    assert status.decision_request is not None
    request = status.decision_request
    assert request.decision_type == SELECT_UNIT_SPLIT_MEMBERSHIP_DECISION_TYPE
    status = session.submit_option(
        request_id=request.request_id,
        option_id="split",
        result_id="choose-split",
    )
    for _ in range(6 if attached else 5):
        assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
        _submit_first(session)
        status = session.advance_until_decision_or_terminal()
    assert session.lifecycle.state is not None
    assert len(session.lifecycle.state.army_definitions[0].unit_splits) == 1
    assert ":split:" not in json.dumps(session.view(viewer_player_id="player-b"))
    assert session.fork().lifecycle.to_payload() == session.lifecycle.to_payload()
    assert ":split:" not in json.dumps(
        session.events_since(EventStreamCursor(), viewer_player_id="player-b")
    )
    assert "unit_split_applied" in json.dumps(
        session.events_since(EventStreamCursor(), viewer_player_id="player-a")
    )
    _deploy_split_units(session)
    _move_one_successor(session)
    assert session.fork().lifecycle.to_payload() == session.lifecycle.to_payload()
    persisted = session.to_persistence_payload()
    replayed = LocalGameSession.from_persistence_payload(persisted)
    assert replayed.lifecycle.to_payload() == session.lifecycle.to_payload()
    assert ":split:" in json.dumps(session.view(viewer_player_id="player-b"))
    state = session.lifecycle.state
    split_army = state.army_definitions[0]
    views = rules_unit_views_from_armies(armies=(split_army,))
    assert len(views) == 2
    target = views[1]
    leaders = tuple(c.unit for c in target.components if c.role == "leader")
    for model in target.alive_models():
        apply_damage_to_model(
            state=state,
            target_unit_instance_id=target.unit_instance_id,
            model_instance_id=model.model_instance_id,
            damage=model.wounds_remaining,
            damage_kind=DamageKind.NORMAL,
        )
        if leaders:
            current = rules_unit_views_from_armies(armies=(state.army_definitions[0],))[1]
            leader_alive = any(
                c.unit.alive_own_models() for c in current.components if c.role == "leader"
            )
            bodyguard_alive = any(
                c.unit.alive_own_models() for c in current.components if c.role == "bodyguard"
            )
            assert conditional_not_leading_source_applies(
                state=state,
                source_unit_instance_id=leaders[0].source_unit_instance_id,
            ) is (leader_alive and not bodyguard_alive)
    after = rules_unit_views_from_armies(armies=(state.army_definitions[0],))
    assert not after[1].alive_models()
    assert after[0].alive_models() == views[0].alive_models()
    validate_attached_rules_unit_identity_after_destruction(
        state=state,
        rules_unit_instance_id=target.unit_instance_id,
    )


def _deploy_split_units(session: LocalGameSession) -> None:
    assert session.lifecycle.state is not None
    for _ in range(100):
        if session.lifecycle.state.stage is GameLifecycleStage.BATTLE:
            break
        request = session.lifecycle.decision_controller.queue.peek_next()
        if request.is_parameterized_submission_request():
            # A client obtains physical ownership from its scoped model projection.
            # It must not derive the current unit ID by truncating the original model ID.
            assert request.actor_id is not None
            model_view = session.view(viewer_player_id=request.actor_id)["battlefield_view"]
            assert model_view is not None
            for entity in model_view["authoritative"]["models_by_id"].values():
                if "split_origin" in entity:
                    assert (
                        entity["split_origin"]["source_unit_instance_id"]
                        in entity["model_instance_id"]
                    )
            status = session.submit_parameterized_payload(
                request_id=request.request_id,
                result_id=f"place:{request.request_id}",
                payload=deployment_placement_payload_for_request(
                    session.lifecycle,
                    request=request,
                    pose_factory=lambda index, player, model_id: Pose.at(
                        3.0 if player == "player-a" else 57.0,
                        10.0
                        + index * 1.8
                        + (
                            12.0
                            if session.lifecycle.state is not None
                            and any(
                                model_id in r.model_ids(1)
                                for a in session.lifecycle.state.army_definitions
                                for r in a.unit_splits
                            )
                            else 0.0
                        ),
                    ),
                ),
            )
        else:
            _submit_first(session)
            status = session.advance_until_decision_or_terminal()
        assert status.status_kind is not LifecycleStatusKind.INVALID, status
    assert session.lifecycle.state.stage is GameLifecycleStage.BATTLE


def _move_one_successor(session: LocalGameSession) -> None:
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    request = session.lifecycle.decision_controller.queue.peek_next()
    for _ in range(20):
        if request.decision_type == SELECT_MOVEMENT_UNIT_DECISION_TYPE:
            break
        _submit_first(session)
        request = session.lifecycle.decision_controller.queue.peek_next()
    assert request.decision_type == SELECT_MOVEMENT_UNIT_DECISION_TYPE
    assert request.actor_id == "player-a"
    views = rules_unit_views_from_armies(armies=(state.army_definitions[0],))
    moving, sibling = views
    before = state.battlefield_state
    sibling_poses = tuple(
        before.model_placement_by_id(m.model_instance_id) for m in sibling.own_models
    )
    session.submit_option(
        request_id=request.request_id,
        option_id=moving.unit_instance_id,
        result_id="split-select-moving-unit",
    )
    action_request = session.lifecycle.decision_controller.queue.peek_next()
    session.submit_option(
        request_id=action_request.request_id,
        option_id="normal_move",
        result_id="split-select-normal-move",
    )
    request = session.lifecycle.decision_controller.queue.peek_next()
    proposal = MovementProposalRequest.from_decision_request_payload(request.payload)
    witness = PathWitness.for_paths(
        tuple(
            path
            for component in moving.components
            for path in straight_line_witness_for_unit(
                session.lifecycle, unit_instance_id=component.unit.unit_instance_id, dx=1.0
            ).model_paths
        )
    )
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="split-movement-proposal",
        payload=validate_json_value(
            MovementProposalPayload(
                proposal_request_id=proposal.request_id,
                proposal_kind=proposal.proposal_kind,
                unit_instance_id=moving.unit_instance_id,
                movement_phase_action="normal_move",
                movement_mode=MovementMode.NORMAL.value,
                witness=witness,
            ).to_payload()
        ),
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status
    assert state.battlefield_state is not None
    for model in moving.own_models:
        old = before.model_placement_by_id(model.model_instance_id)
        current = state.battlefield_state.model_placement_by_id(model.model_instance_id)
        assert current.pose.position.x == old.pose.position.x + 1.0
        assert current.split_origin == old.split_origin
    assert sibling_poses == tuple(
        state.battlefield_state.model_placement_by_id(m.model_instance_id)
        for m in sibling.own_models
    )


def test_split_preserves_selected_membership_and_model_identity() -> None:
    army = mustered_armies(phase11c_config())[0]
    original = army.units[0]
    selected = original.own_model_ids()[::2]
    split = build_split_army(
        army=army,
        unit_instance_id=original.unit_instance_id,
        first_model_ids=selected,
        request_id="test:split:1",
        source_id="test:authorized-split",
        specified_strengths=None,
    )
    assert len(split.units) == 2
    assert split.units[0].own_model_ids() == selected
    assert sorted(model for unit in split.units for model in unit.own_model_ids()) == sorted(
        original.own_model_ids()
    )
    assert {model for unit in split.units for model in unit.own_models} == set(original.own_models)
    assert split.unit_splits[0].source_unit_instance_id == original.unit_instance_id
    assert ArmyDefinition.from_payload(json.loads(json.dumps(split.to_payload()))) == split


@pytest.mark.parametrize("selection", [(), (0,), (0, 0), (0, 1, 2, 3, 4)])
def test_split_rejects_incomplete_or_unbalanced_membership(selection: tuple[int, ...]) -> None:
    army = mustered_armies(phase11c_config())[0]
    unit = army.units[0]
    with pytest.raises(GameLifecycleError):
        build_split_army(
            army=army,
            unit_instance_id=unit.unit_instance_id,
            first_model_ids=tuple(unit.own_model_ids()[index] for index in selection),
            request_id="test:split:1",
            source_id="test:authorized-split",
            specified_strengths=None,
        )


def test_split_models_cannot_be_subdivided_again_or_reassigned_without_lineage() -> None:
    army = mustered_armies(phase11c_config())[0]
    original = army.units[0]
    split = build_split_army(
        army=army,
        unit_instance_id=original.unit_instance_id,
        first_model_ids=original.own_model_ids()[:2],
        request_id="test:split:1",
        source_id="test:authorized-split",
        specified_strengths=None,
    )
    with pytest.raises(GameLifecycleError, match="already"):
        build_split_army(
            army=split,
            unit_instance_id=split.units[0].unit_instance_id,
            first_model_ids=split.units[0].own_model_ids()[:1],
            request_id="test:split:2",
            source_id="test:authorized-split",
            specified_strengths=None,
        )
    with pytest.raises(GameLifecycleError, match=r"lineage|split"):
        replace(split, unit_splits=())


def _session_at_split(config: GameConfig | None = None) -> LocalGameSession:
    session = LocalGameSession()
    session.start(_split_config(config))
    for _ in range(30):
        status = session.advance_until_decision_or_terminal()
        request = status.decision_request
        assert request is not None
        if request.decision_type == SELECT_UNIT_SPLIT_MEMBERSHIP_DECISION_TYPE:
            return session
        _submit_first(session)
    raise AssertionError("Setup did not reach the source-authorized split window.")


def _complete_split(session: LocalGameSession) -> None:
    first = session.lifecycle.decision_controller.queue.peek_next()
    actor = first.actor_id
    status = session.submit_option(
        request_id=first.request_id, option_id="split", result_id="select-split"
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status
    for _ in range(30):
        request = session.lifecycle.decision_controller.queue.peek_next()
        if request.decision_type != SELECT_UNIT_SPLIT_MEMBERSHIP_DECISION_TYPE:
            return
        if request.actor_id != actor:
            return
        status = session.submit_option(
            request_id=request.request_id,
            option_id=request.options[0].option_id,
            result_id=f"result:{request.request_id}",
        )
        assert status.status_kind is not LifecycleStatusKind.INVALID, status
    raise AssertionError("Split membership decisions did not complete.")


@pytest.mark.parametrize("field", ["request_id", "actor_id", "selected_option_id", "payload"])
def test_invalid_split_submission_does_not_pop_or_mutate(field: str) -> None:
    session = _session_at_split()
    request = session.lifecycle.decision_controller.queue.peek_next()
    result = DecisionResult.for_request(
        result_id="invalid-split", request=request, selected_option_id="split"
    )
    invalid = {
        "request_id": replace(result, request_id="stale-request"),
        "actor_id": replace(result, actor_id="player-b"),
        "selected_option_id": replace(result, selected_option_id="invented"),
        "payload": replace(result, payload={"action": "decline"}),
    }[field]
    before = session.lifecycle.to_payload()
    status = session.lifecycle.submit_decision(invalid)
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert session.lifecycle.to_payload() == before


def test_split_membership_request_authenticates_live_source_models_before_pop() -> None:
    session = _session_at_split()
    state = session.lifecycle.state
    assert state is not None
    army = state.army_definitions[0]
    unit = army.units[0]
    model = unit.own_models[0]
    state.army_definitions[0] = replace(
        army,
        units=(
            replace(unit, own_models=(replace(model, wounds_remaining=1), *unit.own_models[1:])),
        ),
    )
    before = session.lifecycle.to_payload()
    request = session.lifecycle.decision_controller.queue.peek_next()
    status = session.submit_option(
        request_id=request.request_id, option_id="split", result_id="drift"
    )
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert session.lifecycle.to_payload() == before


@pytest.mark.parametrize("field", ["source_rule_id", "army_fingerprint", "first_model_ids", "step"])
def test_split_pending_checkpoint_rejects_source_and_membership_drift(field: str) -> None:
    session = _session_at_split()
    payload = session.lifecycle.to_payload()
    pending = payload["decisions"]["queue"]["pending_requests"][0]["payload"]
    assert isinstance(pending, dict)
    pending[field] = validate_json_value(
        {"first_model_ids": ["foreign-model"], "step": 2}.get(field, "drift")
    )
    with pytest.raises(GameLifecycleError, match=r"split|decision|event"):
        GameLifecycle.from_payload(payload)


@pytest.mark.parametrize("extra_models", [0, 1, 2])
def test_ten_model_source_and_attached_leader_support_balancing(extra_models: int) -> None:
    selections = [
        unit_selection(
            unit_selection_id="bodyguard",
            datasheet_id="core-intercessor-like-infantry",
            model_profile_id="core-intercessor-like",
            model_count=10,
        )
    ]
    attachments: list[AttachmentDeclaration] = []
    for role in ("leader", "support")[:extra_models]:
        selections.append(
            unit_selection(
                unit_selection_id=role,
                datasheet_id=f"core-character-{role}",
                model_profile_id=f"core-character-{role}",
                model_count=1,
            )
        )
        attachments.append(
            AttachmentDeclaration(
                source_unit_selection_id=role,
                bodyguard_unit_selection_id="bodyguard",
            )
        )
    session = _session_at_split(
        phase11c_config(
            player_a_units=tuple(selections),
            player_a_attachment_declarations=tuple(attachments),
        )
    )
    _complete_split(session)
    state = session.lifecycle.state
    assert state is not None
    record = state.army_definitions[0].unit_splits[0]
    assert record.used_balanced_fallback is (extra_models > 0)
    assert tuple(len(record.model_ids(i)) for i in (0, 1)) == (
        (10 + extra_models + 1) // 2,
        (10 + extra_models) // 2,
    )
    views = rules_unit_views_from_armies(armies=(state.army_definitions[0],))
    assert sum(len(v.own_models) for v in views) == 10 + extra_models
    assert session.fork().lifecycle.to_payload() == session.lifecycle.to_payload()


@pytest.mark.parametrize("target", ["event", "record", "lineage"])
def test_split_checkpoint_authenticates_partition_and_application(target: str) -> None:
    session = _session_at_split()
    _complete_split(session)
    payload = session.lifecycle.to_payload()
    if target == "event":
        event = next(
            e for e in payload["decisions"]["event_log"] if e["event_type"] == "unit_split_applied"
        )
        assert isinstance(event["payload"], dict)
        event["payload"]["player_id"] = "player-b"
    elif target == "record":
        record = next(
            r
            for r in payload["decisions"]["records"]
            if r["request"]["decision_type"] == SELECT_UNIT_SPLIT_MEMBERSHIP_DECISION_TYPE
        )
        record["result"]["selected_option_id"] = "decline"
        record["result"]["payload"] = {"action": "decline"}
    else:
        assert payload["state"] is not None
        army_payload = payload["state"]["army_definitions"][0]
        assert "unit_splits" in army_payload
        army_payload["unit_splits"][0]["first_model_ids"] = ["foreign"]
    with pytest.raises(GameLifecycleError, match=r"split|decision|event|source"):
        GameLifecycle.from_payload(payload)


def test_unit_split_source_artifact_is_registered_complete_and_hash_pinned() -> None:
    from tools.build_core_unit_splitting_source import ARTIFACT_PATH, AUDIT_PATH, build_payloads

    from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
        core_unit_splitting_2026_09 as source,
    )

    package_payload, audit = build_payloads()
    assert json.loads(ARTIFACT_PATH.read_bytes()) == package_payload
    assert json.loads(AUDIT_PATH.read_bytes()) == audit
    package = source.source_package()
    rules = source.source_rules()
    assert set(package.evidence_required_source_ids) == {rule.source_id for rule in rules}
    assert len(rules) == 2
    for rule in rules:
        assert package.source_catalog.source_text_by_id(rule.source_id).raw_text == rule.source_text
        assert rule.section_id == "01.02.06"
        assert rule.semantic_execution_status == "executable_engine_runtime"
    assert "once" in rules[0].source_text
    assert "Leader/Support" in rules[1].source_text
    assert source.source_evidence_records()
    with pytest.raises(source.UnitSplittingSourceError, match="reviewed pin"):
        source.validate_source_artifact_bytes(ARTIFACT_PATH.read_bytes() + b"\n")


def test_split_preserves_existing_effects_and_one_resource_account() -> None:
    session = _session_at_split()
    state = session.lifecycle.state
    assert state is not None
    original_id = state.army_definitions[0].units[0].unit_instance_id
    effect = PersistingEffect(
        effect_id="test:static-fights-first",
        source_rule_id="test:static-source",
        owner_player_id="player-a",
        target_unit_instance_ids=(original_id,),
        started_battle_round=1,
        expiration=EffectExpiration(EffectExpirationKind.END_OF_BATTLE),
        effect_payload={"effect_kind": "fights_first"},
    )
    state.record_persisting_effect(effect)
    initialize_unit_resource(
        state=state,
        player_id="player-a",
        unit_instance_id=original_id,
        resource_kind="test:token",
        amount=1,
        source_rule_id="test:resource",
    )
    _complete_split(session)
    successors = rules_unit_views_from_armies(armies=(state.army_definitions[0],))
    registry = FightsFirstRegistry.from_state(state)
    for view in successors:
        assert state.persisting_effects_for_unit(view.unit_instance_id) == (effect,)
        assert registry.has_unit(view.unit_instance_id)
        ledger = unit_resource_ledger_for_unit(state=state, unit_instance_id=view.unit_instance_id)
        assert ledger is not None
        assert ledger.unit_instance_id == original_id
        assert ledger.total("test:token") == 1
    assert len(state.unit_resource_ledgers) == 1
    with pytest.raises(GameLifecycleError, match="ambiguous membership"):
        conditional_not_leading_source_applies(state=state, source_unit_instance_id=original_id)


def test_core_splitting_rule_grants_no_permission_and_catalog_consumer_is_registered() -> None:
    assert unit_split_permissions(mustered_armies(phase11c_config())[0]) == ()
    army = mustered_armies(_split_config())[0]
    (permission,) = unit_split_permissions(army)
    ability = next(
        a for a in army.units[0].datasheet_abilities if a.source_id == permission.source_id
    )
    rule = RuleIR.from_payload(cast(RuleIRPayload, ability.rule_ir_payload))
    assert UNIT_SPLIT_CONSUMER_ID in catalog_rule_ir_consumers_for_rule(rule)
    assert UNIT_SPLIT_CONSUMER_ID in catalog_rule_ir_hook_ids_for_rule(rule)


def test_leader_effect_follows_its_source_models_without_granting_to_sibling() -> None:
    session = _session_at_split(
        phase11c_config(
            player_a_units=(
                default_unit_selection("bodyguard"),
                unit_selection(
                    unit_selection_id="leader",
                    datasheet_id="core-character-leader",
                    model_profile_id="core-character-leader",
                    model_count=1,
                ),
            ),
            player_a_attachment_declarations=(
                AttachmentDeclaration(
                    source_unit_selection_id="leader",
                    bodyguard_unit_selection_id="bodyguard",
                ),
            ),
        )
    )
    state = session.lifecycle.state
    assert state is not None
    (original,) = rules_unit_views_from_armies(armies=(state.army_definitions[0],))
    leader = next(c.unit for c in original.components if c.role == "leader")
    bodyguard = next(c.unit for c in original.components if c.role == "bodyguard")
    state.record_persisting_effect(
        PersistingEffect(
            effect_id="test:leader-fights-first",
            source_rule_id="test:leader-source",
            owner_player_id="player-a",
            target_unit_instance_ids=(original.unit_instance_id,),
            started_battle_round=1,
            expiration=EffectExpiration.end_of_battle(),
            effect_payload={
                "effect_kind": GENERIC_RULE_EFFECT_KIND,
                "descriptor_id": CONDITIONAL_LEADER_ABILITY_DESCRIPTOR_ID,
                "required_bodyguard_keyword": bodyguard.keywords[0],
                "context": {"source_unit_instance_id": leader.unit_instance_id},
                "effect": {
                    "kind": "grant_ability",
                    "parameters": [{"key": "ability", "value": "fights_first"}],
                },
            },
        )
    )
    _complete_split(session)
    registry = FightsFirstRegistry.from_state(state)
    successors = rules_unit_views_from_armies(armies=(state.army_definitions[0],))
    assert len(registry.sources) == 1
    for view in successors:
        has_leader = any(m in view.own_models for m in leader.own_models)
        assert (
            conditional_leading_source_unit_applies(
                state=state,
                rules_unit_instance_id=view.unit_instance_id,
                source_unit_instance_id=leader.unit_instance_id,
            )
            is has_leader
        )
        assert registry.has_unit(view.unit_instance_id) is has_leader


@pytest.mark.parametrize("drift", ["source", "timing", "parameters", "duplicate"])
def test_split_permissions_fail_closed_on_unsupported_or_drifted_source(drift: str) -> None:
    army = mustered_armies(_split_config())[0]
    unit = army.units[0]
    (permission,) = unit_split_permissions(army)
    ability = next(a for a in unit.datasheet_abilities if a.source_id == permission.source_id)
    rule = RuleIR.from_payload(cast(RuleIRPayload, ability.rule_ir_payload))
    clause = rule.clauses[0]
    assert clause.trigger is not None
    if drift == "source":
        rule = replace(rule, source_id="drifted-source")
    elif drift == "timing":
        rule = replace(
            rule,
            clauses=(
                replace(
                    clause,
                    trigger=replace(
                        clause.trigger,
                        parameters=(RuleParameter("timing_window", "fight"),),
                    ),
                ),
            ),
        )
    elif drift == "parameters":
        rule = replace(
            rule,
            clauses=(
                replace(
                    clause,
                    effects=(
                        replace(
                            clause.effects[0],
                            parameters=(RuleParameter("optional", "yes"),),
                        ),
                    ),
                ),
            ),
        )
    else:
        rule = replace(
            rule, clauses=(clause, replace(clause, clause_id=f"{clause.clause_id}:copy"))
        )
    altered = replace(ability, rule_ir_payload=cast(CatalogJsonObject, rule.to_payload()))
    altered_unit = replace(
        unit,
        datasheet_abilities=tuple(
            altered if a.ability_id == ability.ability_id else a for a in unit.datasheet_abilities
        ),
    )
    with pytest.raises(GameLifecycleError, match=r"split|Split"):
        unit_split_permissions(replace(army, units=(altered_unit,)))


def _attached_split_config_with_enhancement(*, aura: bool = False) -> GameConfig:
    config = phase11c_config(
        player_a_units=(
            default_unit_selection("bodyguard"),
            unit_selection(
                unit_selection_id="leader",
                datasheet_id="core-character-leader",
                model_profile_id="core-character-leader",
                model_count=1,
            ),
        ),
        player_a_attachment_declarations=(
            AttachmentDeclaration(
                source_unit_selection_id="leader", bodyguard_unit_selection_id="bodyguard"
            ),
        ),
    )
    enhancement = (
        EnhancementDefinition(
            enhancement_id=blood_legion_ir.SLAUGHTERTHIRST_ENHANCEMENT_ID,
            name="Slaughterthirst (Aura)",
            points=25,
            source_id=blood_legion_ir.SLAUGHTERTHIRST_DESCRIPTOR_ID,
        )
        if aura
        else EnhancementDefinition(
            enhancement_id="000009991004",
            name="Targetin Squigs",
            points=15,
            source_id="phase17e:enhancement:orks:more-dakka:000009991004",
        )
    )
    enhancement_id = enhancement.enhancement_id
    catalog = replace(
        config.army_catalog,
        enhancements=(enhancement,),
        datasheets=tuple(
            replace(
                d,
                keywords=replace(
                    d.keywords,
                    keywords=(
                        *d.keywords.keywords,
                        *(("Khorne", "Legiones Daemonica") if aura else ("Orks",)),
                    ),
                ),
            )
            for d in config.army_catalog.datasheets
        ),
        detachments=tuple(
            replace(d, enhancement_ids=(*d.enhancement_ids, enhancement_id))
            for d in config.army_catalog.detachments
        ),
    )
    return replace(
        config,
        army_catalog=catalog,
        army_muster_requests=(
            replace(
                config.army_muster_requests[0],
                enhancement_assignments=(
                    EnhancementAssignment(
                        enhancement_id=enhancement_id,
                        target_unit_selection_id="leader",
                        source_id="test:split-enhancement-assignment",
                    ),
                ),
            ),
            config.army_muster_requests[1],
        ),
    )


@pytest.mark.parametrize("aura", [False, True])
def test_split_enhancement_follows_live_bearer_and_restores(aura: bool) -> None:
    session = _session_at_split(_attached_split_config_with_enhancement(aura=aura))
    state = session.lifecycle.state
    assert state is not None
    original_assignment = state.army_definitions[0].enhancement_assignments
    original_effects = tuple(e.to_payload() for e in state.persisting_effects)
    _complete_split(session)
    assert tuple(e.to_payload() for e in state.persisting_effects) == original_effects
    _deploy_split_units(session)
    restored = session.fork()
    assert restored.lifecycle.to_payload() == session.lifecycle.to_payload()
    replayed = LocalGameSession.from_persistence_payload(session.to_persistence_payload())
    assert replayed.lifecycle.to_payload() == session.lifecycle.to_payload()
    for current in (session, restored, replayed):
        state = current.lifecycle.state
        assert state is not None
        assert state.army_definitions[0].enhancement_assignments == original_assignment
        bundle = object.__getattribute__(current.lifecycle, "_runtime_content_bundle")
        assert type(bundle) is RuntimeContentBundle
        assignments = tuple(
            a
            for a in bundle.activation.selected_enhancement_assignments
            if a.player_id == "player-a"
        )
        assert len(assignments) == 1
        assert assignments[0].target_unit_selection_id == "leader"
        profile = next(
            w
            for w in current.lifecycle.config.army_catalog.wargear
            if w.wargear_id == ("core-leader-blade" if aura else "core-bolt-rifle")
        ).weapon_profiles[0]
        for view in rules_unit_views_from_armies(armies=(state.army_definitions[0],)):
            contains_leader = any(
                c.unit.source_unit_instance_id == "army-alpha:leader" for c in view.components
            )
            selected = runtime_assignment_for_current_bearer(
                state=state,
                player_id="player-a",
                assignments=assignments,
                unit_instance_id=view.unit_instance_id,
            )
            assert selected == (assignments[0] if contains_leader else None)
            for model in view.alive_models():
                if aura:
                    modified = bundle.runtime_modifier_registry.modified_weapon_profile(
                        WeaponProfileModifierContext(
                            state=state,
                            attacking_unit_instance_id=view.unit_instance_id,
                            attacker_model_instance_id=model.model_instance_id,
                            target_unit_instance_id=state.army_definitions[1]
                            .units[0]
                            .unit_instance_id,
                            weapon_profile=profile,
                            source_phase=BattlePhase.FIGHT,
                        )
                    )
                    assert (WeaponKeyword.LANCE in modified.keywords) is contains_leader
                    continue
                value = bundle.runtime_modifier_registry.hit_roll_modifier(
                    HitRollModifierContext(
                        state=state,
                        attacking_unit_instance_id=view.unit_instance_id,
                        attacker_model_instance_id=model.model_instance_id,
                        target_unit_instance_id=state.army_definitions[1].units[0].unit_instance_id,
                        weapon_profile=profile,
                        source_phase=BattlePhase.SHOOTING,
                    )
                )
                assert value == (1 if contains_leader else 0)
    if aura:
        state = replayed.lifecycle.state
        assert state is not None
        army = state.army_definitions[0]
        bearer = enhancement_bearer_unit(army, assignment=original_assignment[0])
        assert bearer.unit_instance_id != "army-alpha:leader"
        model = bearer.own_models[0]
        apply_damage_to_model(
            state=state,
            target_unit_instance_id=bearer.unit_instance_id,
            model_instance_id=model.model_instance_id,
            damage=model.wounds_remaining,
            damage_kind=DamageKind.NORMAL,
        )
        current_bearer = enhancement_bearer_unit(
            state.army_definitions[0], assignment=original_assignment[0]
        )
        assert not current_bearer.own_models[0].is_alive
        assert army.source_unit_by_id("army-alpha:leader").own_models[0].is_alive
        for view in rules_unit_views_from_armies(armies=(state.army_definitions[0],)):
            modified = bundle.runtime_modifier_registry.modified_weapon_profile(
                WeaponProfileModifierContext(
                    state=state,
                    attacking_unit_instance_id=view.unit_instance_id,
                    attacker_model_instance_id=view.alive_models()[0].model_instance_id,
                    target_unit_instance_id=state.army_definitions[1].units[0].unit_instance_id,
                    weapon_profile=profile,
                    source_phase=BattlePhase.FIGHT,
                )
            )
            assert WeaponKeyword.LANCE not in modified.keywords


def test_enhancement_bearer_rejects_foreign_roster_assignment_and_source() -> None:
    army = mustered_armies(_attached_split_config_with_enhancement())[0]
    assignment = army.enhancement_assignments[0]
    with pytest.raises(GameLifecycleError, match="not in the owning army"):
        enhancement_bearer_unit(army, assignment=replace(assignment, source_id="foreign"))
    with pytest.raises(GameLifecycleError, match="unknown bearer unit"):
        current_enhancement_bearer(army, source_unit_instance_id="foreign:leader")


def test_split_deadly_demise_enhancement_keeps_source_and_current_model_ownership() -> None:
    config = _attached_split_config_with_enhancement(aura=True)
    enhancement_id = blood_legion_ir.GATEWAY_UNTO_DAMNATION_ENHANCEMENT_ID
    config = replace(
        config,
        army_catalog=replace(
            config.army_catalog,
            enhancements=(
                EnhancementDefinition(
                    enhancement_id=enhancement_id,
                    name="Gateway unto Damnation",
                    points=10,
                    source_id=blood_legion_ir.GATEWAY_UNTO_DAMNATION_DESCRIPTOR_ID,
                ),
            ),
            detachments=tuple(
                replace(d, enhancement_ids=(enhancement_id,))
                for d in config.army_catalog.detachments
            ),
            datasheets=tuple(
                replace(d, keywords=replace(d.keywords, keywords=(*d.keywords.keywords, "Monster")))
                if d.datasheet_id == "core-character-leader"
                else d
                for d in config.army_catalog.datasheets
            ),
        ),
        army_muster_requests=(
            replace(
                config.army_muster_requests[0],
                enhancement_assignments=(
                    replace(
                        config.army_muster_requests[0].enhancement_assignments[0],
                        enhancement_id=enhancement_id,
                    ),
                ),
            ),
            config.army_muster_requests[1],
        ),
    )
    session = _session_at_split(config)
    state = session.lifecycle.state
    assert state is not None
    model_id = (
        state.army_definitions[0].unit_by_id("army-alpha:leader").own_models[0].model_instance_id
    )
    original = deadly_demise_modifier_for_model(state=state, model_instance_id=model_id)
    assert original is not None
    _complete_split(session)
    for current in (
        session,
        session.fork(),
        LocalGameSession.from_persistence_payload(session.to_persistence_payload()),
    ):
        assert current.lifecycle.to_payload() == session.lifecycle.to_payload()
        state = current.lifecycle.state
        assert state is not None
        assert deadly_demise_modifier_for_model(state=state, model_instance_id=model_id) == original
        assert original.source_unit_instance_id == "army-alpha:leader"
        assert state.unit_instance_id_for_model(model_id) != original.source_unit_instance_id
        for view in rules_unit_views_from_armies(armies=(state.army_definitions[0],)):
            for model in view.own_models:
                if model.model_instance_id != model_id:
                    assert (
                        deadly_demise_modifier_for_model(
                            state=state, model_instance_id=model.model_instance_id
                        )
                        is None
                    )


@pytest.mark.parametrize("target_scope", ["unit", "leader_model", "multiple_aliases"])
def test_split_generic_numerical_effects_apply_after_restore(target_scope: str) -> None:
    config = _attached_split_config_with_enhancement()
    config = replace(
        config,
        army_muster_requests=(
            replace(config.army_muster_requests[0], enhancement_assignments=()),
            config.army_muster_requests[1],
        ),
    )
    session = _session_at_split(config)
    state = session.lifecycle.state
    assert state is not None
    (original,) = rules_unit_views_from_armies(armies=(state.army_definitions[0],))
    leader = next(c.unit for c in original.components if c.role == "leader")
    model_id = leader.own_models[0].model_instance_id
    whole_unit = target_scope != "leader_model"
    targets = (
        (original.unit_instance_id, *original.component_unit_instance_ids)
        if target_scope == "multiple_aliases"
        else (original.unit_instance_id if whole_unit else leader.unit_instance_id,)
    )
    for kind, parameters in (
        ("modify_dice_roll", [{"key": "roll_type", "value": "hit"}, {"key": "delta", "value": 1}]),
        (
            "modify_characteristic",
            [
                {"key": "characteristic", "value": "movement"},
                {"key": "delta", "value": 2},
            ],
        ),
    ):
        state.record_persisting_effect(
            PersistingEffect(
                effect_id=f"test:split:{kind}",
                source_rule_id="test:split-numerical",
                owner_player_id="player-a",
                target_unit_instance_ids=targets,
                started_battle_round=1,
                expiration=EffectExpiration.end_of_battle(),
                effect_payload={
                    "effect_kind": GENERIC_RULE_EFFECT_KIND,
                    "source_id": "test:split-numerical",
                    "rule_id": "test:split-numerical",
                    "rule_ir_hash": "test:split-hash",
                    "clause_id": f"test:{kind}",
                    "effect_index": 0,
                    "target": {"kind": "this_unit" if whole_unit else "this_model"},
                    "effect": {"kind": kind, "parameters": validate_json_value(parameters)},
                    "conditions": [],
                    "context": {"source_model_instance_id": model_id},
                },
            )
        )
    before_effects = tuple(e.to_payload() for e in state.persisting_effects)
    _complete_split(session)
    restored = session.fork()
    assert restored.lifecycle.to_payload() == session.lifecycle.to_payload()
    for current in (session, restored):
        state = current.lifecycle.state
        assert state is not None
        assert tuple(e.to_payload() for e in state.persisting_effects) == before_effects
        profile = current.lifecycle.config.army_catalog.wargear[0].weapon_profiles[0]
        for view in rules_unit_views_from_armies(armies=(state.army_definitions[0],)):
            contains_leader = any(m.model_instance_id == model_id for m in view.own_models)
            assert generic_rule_modified_unit_characteristic(
                UnitCharacteristicModifierContext(
                    state=state,
                    unit_instance_id=view.unit_instance_id,
                    characteristic=Characteristic.MOVEMENT,
                    base_value=6,
                    current_value=6,
                )
            ) == (8 if whole_unit or contains_leader else 6)
            for model in view.alive_models():
                assert generic_rule_hit_roll_modifier(
                    HitRollModifierContext(
                        state=state,
                        attacking_unit_instance_id=view.unit_instance_id,
                        attacker_model_instance_id=model.model_instance_id,
                        target_unit_instance_id=state.army_definitions[1].units[0].unit_instance_id,
                        weapon_profile=profile,
                        source_phase=BattlePhase.SHOOTING,
                    )
                ) == (1 if whole_unit or model.model_instance_id == model_id else 0)
