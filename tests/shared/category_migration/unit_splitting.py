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
    enhancement_bearer_model,
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
                        model_profile_id="core-character-leader",
                        model_index=1,
                        enhancement_id=enhancement_id,
                        target_unit_selection_id="leader",
                        source_id="test:split-enhancement-assignment",
                    ),
                ),
            ),
            config.army_muster_requests[1],
        ),
    )


__all__: list[str] = []
__all__ += ["ArmyDefinition", "AttachmentDeclaration", "BattlePhase"]
__all__ += ["CONDITIONAL_LEADER_ABILITY_DESCRIPTOR_ID", "CatalogAbilitySourceKind"]
__all__ += ["CatalogAbilitySupport", "CatalogJsonObject", "Characteristic", "DamageKind"]
__all__ += ["DatasheetAbilityDescriptor", "DecisionResult", "EffectExpiration"]
__all__ += ["EffectExpirationKind", "EnhancementAssignment", "EnhancementDefinition"]
__all__ += ["GENERIC_RULE_EFFECT_KIND", "EventStreamCursor", "FightsFirstRegistry", "GameConfig"]
__all__ += ["GameLifecycle", "GameLifecycleError", "GameLifecycleStage", "HitRollModifierContext"]
__all__ += ["LifecycleStatusKind", "LocalGameSession", "MovementMode", "MovementProposalPayload"]
__all__ += ["MovementProposalRequest", "ObjectiveRuleScope", "PathWitness", "PersistingEffect"]
__all__ += ["Pose", "RuleIR", "RuleIRPayload", "RuleParameter", "RuleSourceText"]
__all__ += ["SELECT_MOVEMENT_UNIT_DECISION_TYPE", "RuntimeContentBundle"]
__all__ += ["SELECT_UNIT_SPLIT_MEMBERSHIP_DECISION_TYPE", "UNIT_SPLIT_CONSUMER_ID"]
__all__ += ["UnitCharacteristicModifierContext", "WeaponKeyword", "WeaponProfileModifierContext"]
__all__ += ["_attached_split_config_with_enhancement", "_complete_split", "_deploy_split_units"]
__all__ += ["_move_one_successor", "_session_at_split", "_split_config", "_submit_first"]
__all__ += ["apply_damage_to_model", "blood_legion_ir", "build_split_army", "cast"]
__all__ += ["catalog_rule_ir_consumers_for_rule", "catalog_rule_ir_hook_ids_for_rule"]
__all__ += ["compile_rule_source_text", "conditional_leading_source_unit_applies"]
__all__ += ["conditional_not_leading_source_applies", "current_enhancement_bearer"]
__all__ += ["deadly_demise_modifier_for_model", "default_unit_selection"]
__all__ += ["deployment_placement_payload_for_request", "enhancement_bearer_model"]
__all__ += ["enhancement_bearer_unit", "generic_rule_hit_roll_modifier"]
__all__ += ["generic_rule_modified_unit_characteristic", "initialize_unit_resource", "json"]
__all__ += ["keyword_source", "mustered_armies", "phase11c_config", "pytest", "replace"]
__all__ += ["rules_unit_views_from_armies", "runtime_assignment_for_current_bearer"]
__all__ += ["straight_line_witness_for_unit", "unit_resource_ledger_for_unit", "unit_selection"]
__all__ += ["unit_split_permissions", "validate_attached_rules_unit_identity_after_destruction"]
__all__ += ["validate_json_value"]
