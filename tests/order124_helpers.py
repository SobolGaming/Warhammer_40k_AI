"""Authenticate the selected retained Core exemplar before compiling its ability."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import cast

from tools.core_rules_order84_capture import fingerprint

from tests.order122_helpers import submit_quiet_choice
from tests.phase13b_shooting_declaration_helpers import (
    _canonical_catalog,
    _compact_intercessor_catalog,
    _config,
    _mustered_armies,
    _proposal_from_request,
    _shooting_lifecycle,
)
from tests.phase15c_fight_order_helpers import unit_placement_at
from tests.psychic_modifier_helpers import pending_request, submit_fixture_request
from tests.setup_completion_helpers import record_primary_turn_start_evidence_for_fixture
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.datasheet import (
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
    CatalogJsonObject,
    DatasheetAbilityDescriptor,
)
from warhammer40k_core.core.weapon_profiles import AttackProfile, DamageProfile, WeaponKeyword
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.game_state import (
    GameState,
    SecondaryMissionChoice,
    SecondaryMissionMode,
)
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.list_validation import AttachmentDeclaration
from warhammer40k_core.engine.movement_proposals import (
    MovementProposalPayload,
    MovementProposalRequest,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleStage, LifecycleStatusKind
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.reaction_queue import ReactionQueue
from warhammer40k_core.engine.rules_unit_placement import RulesUnitPlacement
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.objective_terminology import ObjectiveRuleScope
from warhammer40k_core.rules.rule_compiler import CompiledRuleSource, compile_rule_source_text
from warhammer40k_core.rules.source_data import RuleSourceText

SOURCE_ROW_ID = "rule:02:02.03.01:1"
SOURCE_ID = f"{SOURCE_ROW_ID}:example"
SOURCE_HASH = "30091dfbc59e53fb250c880610847a3a3f1da9c223f748761381b9d81fa37018"
KEYWORDS = ("INFANTRY", "CHARACTER", "PSYKER", "VEHICLE", "TRANSPORT")
SHOOTER = "army-alpha:shooter"
TARGET = "army-beta:enemy"
OBJECTIVE = "phase13b-remote-objective"


def nested_source() -> CompiledRuleSource:
    rows = json.loads(
        (
            Path(__file__).resolve().parents[1] / "data/source_audits/order97/selected-sources.json"
        ).read_text(encoding="utf-8")
    )
    row = next(row for row in rows if row["row_id"] == SOURCE_ROW_ID)
    assert row["source_sha256"] == SOURCE_HASH
    for block in row["blocks"]:
        assert fingerprint(block["value"]) == block["sha256"]
    # Retain the actual ability in blocks 2-4, excluding the introductory quotation
    # and typographic control delimiters. This is a fixture excerpt, not admission.
    intro = row["blocks"][1]["value"].removeprefix("For example, an ability reads: \u2018")
    bullets = [block["value"] for block in row["blocks"][2:4]]
    text = "\n".join((intro, *bullets)).removesuffix("\u2019")
    for delimiter in ("\x01", "\x02", "\x05", "\x06"):
        text = text.replace(delimiter, "")
    text = text.replace("• ", "- ").replace("Or:If", "Or: If")
    return compile_rule_source_text(
        RuleSourceText.from_raw(
            source_id=SOURCE_ID, raw_text=text, objective_scope=ObjectiveRuleScope.CORE_RULES
        ),
        source_keyword_sequence_parts=KEYWORDS,
    )


def nested_session(
    *,
    improved: bool = True,
    closest: bool = True,
    attached: bool = False,
    source_present: bool = True,
    game_id: str = "order124-nested",
    control: str = "opponent",
    tied_closest: bool = False,
    nearest_target_ineligible: bool = False,
    advanced: bool = False,
) -> LocalGameSession:
    """Canonical catalog fixture followed by a real Movement/Shooting boundary."""
    compiled = nested_source()
    descriptor = DatasheetAbilityDescriptor(
        ability_id="order124-nested",
        name="Core nested condition fixture",
        source_id=SOURCE_ID,
        source_kind=CatalogAbilitySourceKind.DATASHEET,
        support=CatalogAbilitySupport.GENERIC_RULE_IR,
        effect_description=compiled.source_text.normalized_text,
        rule_ir_payload=cast(CatalogJsonObject, compiled.rule_ir.to_payload()),
    )
    catalog = _compact_intercessor_catalog(_canonical_catalog())
    catalog = replace(
        catalog,
        datasheets=tuple(
            replace(sheet, abilities=(*sheet.abilities, descriptor))
            if source_present
            and sheet.datasheet_id
            == ("core-character-leader" if attached else "core-intercessor-like-infantry")
            else sheet
            for sheet in catalog.datasheets
        ),
        wargear=tuple(
            replace(
                item,
                weapon_profiles=tuple(
                    replace(
                        profile,
                        attack_profile=AttackProfile.fixed(6),
                        damage_profile=DamageProfile.fixed(1),
                        keywords=(WeaponKeyword.ASSAULT,)
                        if advanced and item.wargear_id == "core-bolt-rifle"
                        else (),
                        abilities=(),
                        range_profile=replace(profile.range_profile, distance_inches=48),
                    )
                    if profile.range_profile.distance_inches is not None
                    else profile
                    for profile in item.weapon_profiles
                ),
            )
            for item in catalog.wargear
        ),
    )
    specs: tuple[tuple[str, str, str, int], ...] = (
        ("shooter", "core-intercessor-like-infantry", "core-intercessor-like", 1),
    )
    if attached:
        specs += (("leader", "core-character-leader", "core-character-leader", 1),)
    if control in {"friendly", "tied"}:
        specs += (
            (
                "controller",
                "core-intercessor-like-infantry",
                "core-intercessor-like",
                2 if control == "friendly" else 1,
            ),
        )
    assert control in {"opponent", "friendly", "tied", "uncontrolled"}
    if advanced:
        assert control == "opponent"
        assert improved
        assert closest
        specs += (("observer", "core-intercessor-like-infantry", "core-intercessor-like", 1),)
    builder = _advanced_movement_fixture if advanced else _shooting_lifecycle
    lifecycle, units = builder(
        alpha_unit_ids=("shooter",),
        alpha_unit_specs=specs,
        alpha_attachment_declarations=(AttachmentDeclaration("leader", "shooter"),)
        if attached
        else (),
        enemy_unit_specs=(
            ("enemy", "core-character-leader", "core-character-leader", 1),
            ("other", "core-character-leader", "core-character-leader", 1),
        ),
        catalog=catalog,
        game_id=game_id,
    )
    state = lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    battlefield = replace(state.battlefield_state, terrain_features=())
    poses = {
        "shooter": Pose.at(75, 55),
        "leader": Pose.at(75, 56.65),
        "enemy": Pose.at(94 if improved else 88, 55),
        "other": Pose.at(97 if closest else 82, 59),
        "controller": Pose.at(95, 51),
        "observer": Pose.at(70, 52),
    }
    if control == "uncontrolled":
        poses["enemy"] = Pose.at(88, 55)
        poses["other"] = Pose.at(90, 59)
    if tied_closest:
        poses["other"] = Pose.at(75, 36)
    if nearest_target_ineligible:
        assert control == "tied"
        poses["controller"] = Pose.at(95, 52.5)
    for key, unit in units.items():
        alpha = key in {"shooter", "leader", "controller", "observer"}
        battlefield = battlefield.with_unit_placement(
            unit_placement_at(
                unit,
                army_id="army-alpha" if alpha else "army-beta",
                player_id="player-a" if alpha else "player-b",
                poses=tuple(
                    Pose.at(poses[key].position.x + index * 1.4, poses[key].position.y)
                    for index in range(len(unit.own_models))
                ),
            )
        )
    state.replace_battlefield_state(battlefield)
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.MOVEMENT)
    state.shooting_phase_state = None
    session = LocalGameSession(GameLifecycle.from_payload(lifecycle.to_payload()))
    attacker_unit_id = rules_unit_view_by_id(state=state, unit_instance_id=SHOOTER).unit_instance_id
    selected_advance = False
    for index in range(40):
        request = pending_request(session)
        if request.decision_type == "select_shooting_unit":
            return session
        result_id = f"order124-movement-{index}"
        if advanced and request.decision_type == "select_movement_unit" and not selected_advance:
            selected_advance = True
            session.submit_option(
                request_id=request.request_id, option_id=attacker_unit_id, result_id=result_id
            )
        elif (
            advanced
            and request.decision_type == "select_movement_action"
            and any(
                isinstance(option.payload, dict)
                and option.payload.get("movement_phase_action") == "advance"
                and option.payload.get("unit_instance_id") == attacker_unit_id
                for option in request.options
            )
        ):
            option = next(
                option
                for option in request.options
                if isinstance(option.payload, dict)
                and option.payload.get("movement_phase_action") == "advance"
                and option.payload.get("unit_instance_id") == attacker_unit_id
            )
            session.submit_option(
                request_id=request.request_id, option_id=option.option_id, result_id=result_id
            )
        elif advanced and request.decision_type == "submit_movement_proposal":
            proposal = MovementProposalRequest.from_decision_request_payload(request.payload)
            assert proposal.unit_instance_id == attacker_unit_id
            assert proposal.movement_phase_action == "advance"
            context = proposal.context or {}
            mode = context["movement_mode"]
            assert isinstance(mode, str)
            current_state = session.lifecycle.state
            assert current_state is not None
            assert current_state.battlefield_state is not None
            placement = RulesUnitPlacement.from_battlefield(
                view=rules_unit_view_by_id(
                    state=current_state, unit_instance_id=proposal.unit_instance_id
                ),
                battlefield_state=current_state.battlefield_state,
            )
            payload = MovementProposalPayload(
                proposal_request_id=proposal.request_id,
                proposal_kind=proposal.proposal_kind,
                unit_instance_id=proposal.unit_instance_id,
                movement_phase_action=proposal.movement_phase_action,
                witness=PathWitness.for_paths(
                    tuple(
                        (model.model_instance_id, (model.pose, model.pose))
                        for model in placement.model_placements
                    )
                ),
                movement_mode=mode,
            )
            status = session.submit_parameterized_payload(
                request_id=request.request_id,
                result_id=result_id,
                payload=validate_json_value(payload.to_payload()),
            )
            assert status.status_kind is not LifecycleStatusKind.INVALID, status.payload
        else:
            submit_quiet_choice(session, request, result_id=result_id)
    raise AssertionError("Real Movement boundary did not reach Shooting.")


def declare_nested_shot(
    session: LocalGameSession, *, shooting_type: str = "normal"
) -> DecisionRequest:
    state = session.lifecycle.state
    assert state is not None
    request = pending_request(session)
    unit_id = rules_unit_view_by_id(state=state, unit_instance_id=SHOOTER).unit_instance_id
    session.submit_option(
        request_id=request.request_id, option_id=unit_id, result_id="order124:unit"
    )
    request = pending_request(session)
    session.submit_option(
        request_id=request.request_id, option_id=shooting_type, result_id="order124:type"
    )
    request = pending_request(session)
    proposal = _proposal_from_request(request=request, target_unit_id=TARGET)
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="order124:declaration",
        payload=validate_json_value(proposal.to_payload()),
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status.payload
    return pending_request(session)


def finish_nested_shot(
    session: LocalGameSession, *, use_reroll: bool
) -> tuple[DecisionRequest, ...]:
    requests: list[DecisionRequest] = []
    for index in range(100):
        request = pending_request(session)
        state = session.lifecycle.state
        assert state is not None
        if state.current_battle_phase is not BattlePhase.SHOOTING:
            return tuple(requests)
        if request.decision_type == "select_shooting_unit":
            return tuple(requests)
        requests.append(request)
        if request.decision_type == "select_dice_reroll":
            option = next(
                option
                for option in request.options
                if ("decline" not in option.option_id) is use_reroll
            )
            status = session.submit_option(
                request_id=request.request_id,
                result_id=f"order124-reroll-{index}",
                option_id=option.option_id,
            )
            assert status.status_kind is not LifecycleStatusKind.INVALID, status.payload
        else:
            submit_fixture_request(session, request)
    raise AssertionError("Real nested shot did not complete.")


def _advanced_movement_fixture(
    *,
    alpha_unit_ids: tuple[str, ...],
    alpha_unit_specs: tuple[tuple[str, str, str, int], ...],
    alpha_attachment_declarations: tuple[AttachmentDeclaration, ...],
    enemy_unit_specs: tuple[tuple[str, str, str, int], ...],
    catalog: ArmyCatalog,
    game_id: str,
) -> tuple[GameLifecycle, dict[str, UnitInstance]]:
    # Assemble the standard fixture before its first turn-start evidence. A second
    # shooter keeps completed-shot continuations in this real Shooting phase.
    config = _config(
        alpha_unit_ids=alpha_unit_ids,
        alpha_datasheets=None,
        alpha_unit_specs=alpha_unit_specs,
        alpha_attachment_declarations=alpha_attachment_declarations,
        enemy_datasheet=None,
        enemy_unit_specs=enemy_unit_specs,
        catalog=catalog,
        game_id=game_id,
    )
    armies = _mustered_armies(config)
    units = {unit.unit_instance_id.split(":", 1)[1]: unit for army in armies for unit in army.units}
    mission = config.mission_setup
    assert mission is not None
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="phase13b-battlefield",
        battlefield_width_inches=mission.battlefield_width_inches,
        battlefield_depth_inches=mission.battlefield_depth_inches,
        armies=armies,
    )
    battlefield = replace(scenario.battlefield_state, terrain_features=())
    poses = {
        "shooter": Pose.at(75, 55),
        "leader": Pose.at(75, 56.65),
        "observer": Pose.at(70, 52),
        "enemy": Pose.at(94, 55),
        "other": Pose.at(97, 59),
    }
    for key, unit in units.items():
        alpha = key in {"shooter", "leader", "observer"}
        battlefield = battlefield.with_unit_placement(
            unit_placement_at(
                unit,
                army_id="army-alpha" if alpha else "army-beta",
                player_id="player-a" if alpha else "player-b",
                poses=(poses[key],),
            )
        )
    state = GameState.from_config(config)
    decisions = DecisionController()
    for army in armies:
        state.record_army_definition(army)
    state.record_battlefield_state(battlefield)
    for player in state.player_ids:
        state.record_secondary_mission_choice(
            SecondaryMissionChoice(
                player_id=player,
                mode=SecondaryMissionMode.FIXED,
                fixed_mission_ids=("assassination", "bring_it_down"),
            )
        )
    state.stage = GameLifecycleStage.BATTLE
    state.setup_step_index = None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.MOVEMENT)
    state.battle_round = 1
    state.active_player_id = "player-a"
    record_primary_turn_start_evidence_for_fixture(state, decisions=decisions)
    return GameLifecycle.from_payload(
        {
            "config": config.to_payload(),
            "state": state.to_payload(),
            "decisions": decisions.to_payload(),
            "reaction_queue": ReactionQueue().to_payload(),
            "parameterized_movement_proposals": True,
        }
    ), units
