from __future__ import annotations

import json
from dataclasses import replace
from typing import cast

import pytest
from tests.deployment_submission_helpers import submit_all_deployments_if_pending

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.adapters.projection import (
    RULES_CATALOG_VIEW_SCHEMA_VERSION,
    project_game_view,
    project_rules_catalog_view,
)
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.army_mustering import ArmyMusterRequest
from warhammer40k_core.engine.decision_record import DecisionRecord, DecisionRecordPayload
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.game_state import GameConfig, GameState
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    ModelProfileSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus, LifecycleStatusKind
from warhammer40k_core.engine.phases.movement import SELECT_MOVEMENT_UNIT_DECISION_TYPE
from warhammer40k_core.engine.setup_flow import SECONDARY_MISSION_DECISION_TYPE
from warhammer40k_core.engine.unit_factory import ModelInstance
from warhammer40k_core.interfaces.cli import (
    render_decision_request_for_cli,
    submit_cli_choice,
)
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack


def test_cli_adapter_renders_finite_options_and_records_normal_decision() -> None:
    session = LocalGameSession()
    session.start(_config(game_id="phase18a-cli-game"))
    status = session.advance_until_decision_or_terminal()
    request = _decision_request(status)

    prompt = render_decision_request_for_cli(request)
    follow_up = submit_cli_choice(
        lifecycle=session.lifecycle,
        choice="tactical",
        result_id="phase18a-cli-secondary-a",
    )
    record = session.lifecycle.decision_controller.records[-1]
    payload = cast(
        DecisionRecordPayload,
        json.loads(json.dumps(record.to_payload(), sort_keys=True)),
    )

    assert prompt["request_id"] == request.request_id
    assert prompt["decision_type"] == SECONDARY_MISSION_DECISION_TYPE
    assert prompt["actor_id"] == "player-a"
    assert prompt["is_parameterized"] is False
    assert {option["option_id"] for option in prompt["options"]}.issuperset(
        {
            "tactical",
            "fixed:assassination:bring_it_down",
        }
    )
    assert follow_up.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert record.result.selected_option_id == "tactical"
    assert DecisionRecord.from_payload(payload).to_payload() == record.to_payload()


def test_invalid_cli_choice_is_rejected_without_queue_or_record_mutation() -> None:
    session = LocalGameSession()
    session.start(_config(game_id="phase18a-cli-invalid-game"))
    status = session.advance_until_decision_or_terminal()
    request = _decision_request(status)

    with pytest.raises(GameLifecycleError, match="out of range"):
        submit_cli_choice(
            lifecycle=session.lifecycle,
            choice="99",
            result_id="phase18a-cli-invalid-choice",
        )

    assert session.lifecycle.decision_controller.queue.pending_requests == (request,)
    assert session.lifecycle.decision_controller.records == ()


def test_rules_catalog_projection_exposes_cacheable_static_display_records() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    payload = project_rules_catalog_view(catalog=catalog)
    round_trip = json.loads(json.dumps(payload, sort_keys=True))

    assert payload["projection_schema"] == RULES_CATALOG_VIEW_SCHEMA_VERSION
    assert payload["catalog_id"] == catalog.catalog_id
    assert len(payload["source_hash"]) == 64
    assert "core-intercessor-like-infantry" in payload["datasheet_display_by_id"]
    assert "core-intercessor-like" in payload["model_profile_display_by_id"]
    assert payload["wargear_display_by_id"]["core-bolt-rifle"] == {
        "wargear_id": "core-bolt-rifle",
        "display_name": "Core bolt rifle",
        "weapon_profile_ids": ["core-bolt-rifle:standard"],
        "profile": {
            "wargear_id": "core-bolt-rifle",
            "name": "Core bolt rifle",
            "weapon_profiles": [
                payload["weapon_profile_display_by_id"]["core-bolt-rifle:standard"]["profile"]
            ],
        },
    }
    assert "core-bolt-rifle:standard" in payload["weapon_profile_display_by_id"]
    assert "core-marine-force" in payload["faction_display_by_id"]
    assert "core-combined-arms" in payload["detachment_display_by_id"]
    assert payload["enhancement_display_by_id"] == {}
    assert (
        "core-intercessor-like-infantry:default-wargear"
        in (payload["wargear_option_display_by_id"])
    )
    assert payload["base_size_display_by_id"]["base-size:core-intercessor-like"] == {
        "base_size_id": "base-size:core-intercessor-like",
        "kind": "circular",
        "diameter_mm": 32.0,
        "length_mm": None,
        "width_mm": None,
    }
    assert validate_json_value(round_trip) == payload


def test_game_view_exposes_issue145_unit_model_datacard_join_without_unknowns() -> None:
    session, _status = _local_session_at_movement_unit_selection(game_id="phase18a-issue145-game")
    view = project_game_view(lifecycle=session.lifecycle, viewer_player_id="player-a")
    battlefield = cast(dict[str, JsonValue], view["battlefield_state"])
    placed_army = cast(list[dict[str, JsonValue]], battlefield["placed_armies"])[0]
    unit_placement = cast(list[dict[str, JsonValue]], placed_army["unit_placements"])[0]
    model_placement = cast(list[dict[str, JsonValue]], unit_placement["model_placements"])[0]
    unit_id = cast(str, unit_placement["unit_instance_id"])
    model_id = cast(str, model_placement["model_instance_id"])
    unit_display = view["unit_display_by_id"][unit_id]
    model_display = view["model_display_by_id"][model_id]

    rules_catalog = project_rules_catalog_view(catalog=session.lifecycle.config.army_catalog)
    assert view["rules_catalog"] == {
        "projection_schema": rules_catalog["projection_schema"],
        "catalog_id": rules_catalog["catalog_id"],
        "ruleset_id": rules_catalog["ruleset_id"],
        "source_package_id": rules_catalog["source_package_id"],
        "source_hash": rules_catalog["source_hash"],
    }
    assert unit_display["unit_display_name"] == "CORE Intercessor-like Infantry"
    assert unit_display["datasheet_id"] == "core-intercessor-like-infantry"
    assert model_id in unit_display["model_instance_ids"]
    assert model_display["model_profile_id"] == "core-intercessor-like"
    base_size = model_display["base_size"]
    assert base_size is not None
    assert base_size["diameter_mm"] == 32.0
    assert set(model_display["current_characteristics"]) == {"M", "T", "SV", "W", "LD", "OC"}
    assert {
        key: characteristic["final"]
        for key, characteristic in model_display["current_characteristics"].items()
    } == {"M": 6, "T": 4, "SV": 3, "W": 2, "LD": 6, "OC": 2}
    assert all(
        characteristic["value_kind"] != "unknown"
        for characteristic in model_display["current_characteristics"].values()
    )


def test_live_projection_reports_engine_resolved_characteristic_modifiers() -> None:
    session, _status = _local_session_at_movement_unit_selection(game_id="phase18a-modifier-game")
    state = _session_state(session)
    _replace_first_model(
        state,
        _model_with_movement_modifier(
            _first_model(state),
            modifier_id="phase18a-move-plus-one",
            movement=7,
        ),
    )

    view = project_game_view(lifecycle=session.lifecycle, viewer_player_id="player-a")
    model_id = _first_model(state).model_instance_id
    model_display = view["model_display_by_id"][model_id]
    current_movement = model_display["current_characteristics"]["M"]

    assert model_display["base_characteristics"]["M"]["final"] == 6
    assert current_movement["final"] == 7
    assert current_movement["applied_modifier_ids"] == ["phase18a-move-plus-one"]
    assert model_display["visible_modifiers"] == [
        {
            "modifier_id": "phase18a-move-plus-one",
            "source_kind": "engine_resolved_characteristic",
            "source_id": "phase18a-move-plus-one",
            "target": {
                "target_kind": "model_characteristic",
                "model_instance_id": model_id,
                "characteristic": "movement",
                "characteristic_label": "M",
            },
            "applies_status": "applied",
            "public_label": "phase18a-move-plus-one",
            "operation_text": ("Engine-resolved modifier phase18a-move-plus-one applies to M."),
        }
    ]


def test_live_projection_reports_battle_shock_objective_control_modifier() -> None:
    session, _status = _local_session_at_movement_unit_selection(
        game_id="phase18a-battle-shock-game"
    )
    state = _session_state(session)
    model_id = _first_model(state).model_instance_id
    unit_id = state.army_definitions[0].units[0].unit_instance_id
    before = project_game_view(lifecycle=session.lifecycle, viewer_player_id="player-a")

    state.battle_shocked_unit_ids = [unit_id]
    after = project_game_view(lifecycle=session.lifecycle, viewer_player_id="player-a")
    model_display = after["model_display_by_id"][model_id]
    base_oc = model_display["base_characteristics"]["OC"]
    current_oc = model_display["current_characteristics"]["OC"]

    assert before["projection_state_hash"] != after["projection_state_hash"]
    assert before["model_display_by_id"][model_id]["current_characteristics"]["OC"]["final"] == 2
    assert base_oc["final"] == 2
    assert current_oc == {
        "characteristic": "objective_control",
        "label": "OC",
        "value_kind": "replacement_dash",
        "raw": 0,
        "base": 0,
        "final": 0,
        "display_value": "-",
        "applied_modifier_ids": ["battle_shock"],
        "redaction": {"hidden": False, "reason": None},
    }
    assert model_display["visible_modifiers"] == [
        {
            "modifier_id": "battle_shock",
            "source_kind": "engine_resolved_characteristic",
            "source_id": "battle_shock",
            "target": {
                "target_kind": "model_characteristic",
                "model_instance_id": model_id,
                "characteristic": "objective_control",
                "characteristic_label": "OC",
            },
            "applies_status": "applied",
            "public_label": "battle_shock",
            "operation_text": "Engine-resolved modifier battle_shock applies to OC.",
        }
    ]


def test_game_view_projection_hash_changes_for_live_wound_display_state() -> None:
    session, _status = _local_session_at_movement_unit_selection(game_id="phase18a-hash-game")
    state = _session_state(session)
    before = project_game_view(lifecycle=session.lifecycle, viewer_player_id="player-a")
    wounded_model = replace(_first_model(state), wounds_remaining=1)
    _replace_first_model(state, wounded_model)
    after = project_game_view(lifecycle=session.lifecycle, viewer_player_id="player-a")

    assert before["projection_state_hash"] != after["projection_state_hash"]
    assert after["model_display_by_id"][wounded_model.model_instance_id]["wounds_remaining"] == 1


def test_projection_payload_consumption_does_not_mutate_authoritative_state() -> None:
    session, _status = _local_session_at_movement_unit_selection(game_id="phase18a-read-only-game")
    view = project_game_view(lifecycle=session.lifecycle, viewer_player_id="player-a")
    unit_id = "army-alpha:intercessor-unit-1"
    view["unit_display_by_id"][unit_id]["unit_display_name"] = "Mutated UI label"

    refreshed = project_game_view(lifecycle=session.lifecycle, viewer_player_id="player-a")

    assert refreshed["unit_display_by_id"][unit_id]["unit_display_name"] == (
        "CORE Intercessor-like Infantry"
    )


def test_non_owner_predeployment_projection_does_not_expose_unplaced_opponent_units() -> None:
    session = LocalGameSession()
    session.start(_config(game_id="phase18a-predeployment-game"))
    session.advance_until_decision_or_terminal()

    player_a_view = project_game_view(lifecycle=session.lifecycle, viewer_player_id="player-a")

    assert "army-alpha:intercessor-unit-1" in player_a_view["unit_display_by_id"]
    assert "army-beta:intercessor-unit-2" not in player_a_view["unit_display_by_id"]


def _local_session_at_movement_unit_selection(
    *,
    game_id: str,
) -> tuple[LocalGameSession, LifecycleStatus]:
    session = LocalGameSession()
    session.start(_config(game_id=game_id))
    first_status = session.advance_until_decision_or_terminal()
    assert _decision_request(first_status).decision_type == SECONDARY_MISSION_DECISION_TYPE
    second_status = session.submit_option(
        option_id="fixed:assassination:bring_it_down",
        result_id=f"{game_id}-secondary-a",
    )
    assert _decision_request(second_status).decision_type == SECONDARY_MISSION_DECISION_TYPE
    movement_status = session.submit_option(
        option_id="fixed:assassination:bring_it_down",
        result_id=f"{game_id}-secondary-b",
    )
    movement_status = submit_all_deployments_if_pending(
        session.lifecycle,
        movement_status,
        result_id_prefix=f"{game_id}-deploy",
    )
    assert _decision_request(movement_status).decision_type == SELECT_MOVEMENT_UNIT_DECISION_TYPE
    return session, movement_status


def _config(*, game_id: str) -> GameConfig:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    return GameConfig(
        game_id=game_id,
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(
            descriptor_version="core-v2-phase18a-test"
        ),
        army_catalog=catalog,
        army_muster_requests=(
            _army_muster_request(
                catalog=catalog,
                player_id="player-a",
                army_id="army-alpha",
                unit_selection_id="intercessor-unit-1",
            ),
            _army_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_selection_id="intercessor-unit-2",
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring_it_down", "cleanse"),
        mission_setup=MissionSetup.from_mission_pack(
            mission_pack=chapter_approved_2026_27_mission_pack(),
            mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-3",
            terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-3",
            attacker_player_id="player-a",
            defender_player_id="player-b",
        ),
    )


def _army_muster_request(
    *,
    catalog: ArmyCatalog,
    player_id: str,
    army_id: str,
    unit_selection_id: str,
) -> ArmyMusterRequest:
    return ArmyMusterRequest(
        army_id=army_id,
        player_id=player_id,
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id="core-marine-force",
            detachment_ids=("core-combined-arms",),
        ),
        unit_selections=(
            UnitMusterSelection(
                unit_selection_id=unit_selection_id,
                datasheet_id="core-intercessor-like-infantry",
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-intercessor-like",
                        model_count=5,
                    ),
                ),
            ),
        ),
    )


def _decision_request(status: LifecycleStatus) -> DecisionRequest:
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request is not None
    return status.decision_request


def _session_state(session: LocalGameSession) -> GameState:
    state = session.lifecycle.state
    assert state is not None
    return state


def _first_model(state: GameState) -> ModelInstance:
    return state.army_definitions[0].units[0].own_models[0]


def _model_with_movement_modifier(
    model: ModelInstance,
    *,
    modifier_id: str,
    movement: int,
) -> ModelInstance:
    characteristics: list[CharacteristicValue] = []
    for value in model.characteristics:
        if value.characteristic is Characteristic.MOVEMENT:
            characteristics.append(
                CharacteristicValue(
                    characteristic=value.characteristic,
                    raw=value.raw,
                    base=value.base,
                    final=movement,
                    applied_modifier_ids=(modifier_id,),
                    value_kind=value.value_kind,
                )
            )
            continue
        characteristics.append(value)
    return replace(model, characteristics=tuple(characteristics))


def _replace_first_model(state: GameState, model: ModelInstance) -> None:
    army = state.army_definitions[0]
    unit = army.units[0]
    updated_unit = replace(unit, own_models=(model, *unit.own_models[1:]))
    updated_army = replace(army, units=(updated_unit, *army.units[1:]))
    state.army_definitions = [updated_army, *state.army_definitions[1:]]
