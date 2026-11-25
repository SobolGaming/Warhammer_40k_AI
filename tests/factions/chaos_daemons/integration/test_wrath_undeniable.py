"""Wrath Undeniable through the native Fight decision and destruction owners."""

from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest

from tests.daemons_native_source_helpers import native_definitions
from tests.save7_allocation_helpers import BLOODLETTERS
from tests.support.faction_batch01 import LORD, Scene, anchor, events, locate, scene, selection
from tests.support.section02_fixtures import Section02Definitions
from tests.support.section04_fixtures import pending, weapon_rows
from tests.support.section12_fixtures import melee_payload, move_payload
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.detachment import DetachmentDefinition
from warhammer40k_core.engine.command_points import CommandPointSourceKind
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.engine.replay import ReplayRunner
from warhammer40k_core.engine.retained_destruction_state import retained_destructions
from warhammer40k_core.engine.stratagems import stratagem_decline_payload
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_blood_legion_ir_support_2026_27 as wrath,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_detachments_2026_27 as identities,
)

TARGET = "own:target"
ATTACKER = "foe:attacker"
WRATH_OPTION = f"use-stratagem:{wrath.WRATH_UNDENIABLE_STRATAGEM_ID}:target:{TARGET}"
DETACHMENTS = {"chaos-daemons": "blood-legion", "emperors-children": "court-of-the-phoenician"}


@pytest.fixture(scope="module")
def wrath_definitions(selected_army_source_index: Path | None) -> Section02Definitions:
    native = native_definitions(selected_army_source_index)
    catalog = native.package.army_catalog
    faction_ids = {"CD": "chaos-daemons", "EC": "emperors-children"}
    factions = tuple(
        replace(faction, faction_id=faction_ids[faction.faction_id]) for faction in catalog.factions
    )
    detachments = tuple(
        DetachmentDefinition(
            canonical_detachment_id=row.detachment_id,
            detachment_id=row.detachment_id,
            name=row.name,
            faction_id=faction.faction_id,
            detachment_point_cost=row.detachment_point_cost,
            unit_datasheet_ids=tuple(
                sheet.datasheet_id
                for sheet in catalog.datasheets
                if set(sheet.keywords.faction_keywords).intersection(faction.faction_keywords)
            ),
            force_disposition_ids=("purge-the-foe", "take-and-hold"),
            source_ids=row.source_ids,
        )
        for faction in factions
        for row in identities.detachment_rows()
        if row.detachment_id == DETACHMENTS[faction.faction_id]
    )
    return Section02Definitions(
        replace(
            native.package,
            army_catalog=replace(catalog, factions=factions, detachments=detachments),
        ),
        native.preparation_seconds,
    )


def _scene(definitions: Section02Definitions, *, seed_label: str, active: str) -> Scene:
    battle = scene(
        definitions,
        (selection(definitions, BLOODLETTERS, "target"),),
        (selection(definitions, LORD, "attacker"),),
        phase=BattlePhase.FIGHT,
        active=active,
        detachment_id_by_faction=DETACHMENTS,
        seed="wrath-undeniable",
        rng_seed_label=seed_label,
    )
    count = len(battle.units[TARGET].own_models)
    locate(
        battle,
        TARGET,
        tuple(Pose.at(10 - 1.4 * (i % 2), 10 + 1.4 * (i // 2)) for i in range(count)),
    )
    locate(battle, ATTACKER, (Pose.at(12, 10),))
    battle.state.gain_command_points(
        player_id="owner",
        amount=1,
        source_id="wrath-test:cp",
        source_kind=CommandPointSourceKind.OTHER,
    )
    anchor(battle)
    return battle


def _play(battle: Scene, request: DecisionRequest, *, retained_model_id: str | None) -> None:
    payload: JsonValue
    if request.decision_type == "submit_movement_proposal":
        payload = move_payload(request)
    elif request.decision_type == "submit_stratagem_target_proposal":
        payload = stratagem_decline_payload()
    elif request.decision_type == "submit_melee_declaration":
        declaration = cast(dict[str, JsonValue], melee_payload(request, attack=False))
        entries: list[JsonValue] = []
        selected: set[tuple[str, str | None]] = set()
        for row in weapon_rows(request):
            targets = cast(list[str], row["engaged_target_unit_instance_ids"])
            if not targets:
                continue
            model_id = cast(str, row["model_instance_id"])
            profile_key = cast(str, row["weapon_instance_id"]) if row["is_extra_attacks"] else None
            key = (model_id, profile_key)
            if key in selected:
                continue
            selected.add(key)
            entries.append(
                {
                    "attacker_model_instance_id": model_id,
                    "wargear_id": row["wargear_id"],
                    "weapon_profile_id": row["weapon_profile_id"],
                    "weapon_instance_id": row["weapon_instance_id"],
                    "selected_weapon_ability_ids": [],
                    "target_allocations": [{"target_unit_instance_id": targets[0]}],
                }
            )
        if request.actor_id == "owner" and retained_model_id is not None:
            assert (retained_model_id, None) in selected
        declaration["declarations"] = entries
        payload = declaration
    else:
        option = next(
            (
                o
                for o in request.options
                if o.option_id in {"decline", "keep", "keep_all_modifiers"}
            ),
            request.options[0],
        )
        result = battle.session.submit_option(
            request_id=request.request_id,
            result_id=f"{request.request_id}:wrath",
            option_id=option.option_id,
        )
        assert result.status_kind is not LifecycleStatusKind.INVALID, result
        return
    result = battle.session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id=f"{request.request_id}:wrath",
        payload=payload,
    )
    assert result.status_kind is not LifecycleStatusKind.INVALID, result


@pytest.mark.integration
@pytest.mark.parametrize(
    ("active", "seed", "expected_roll"),
    [
        pytest.param("opponent", 3, 4, id="four"),
        pytest.param("opponent", 2, 3, id="three"),
        pytest.param("owner", 1, None, id="already-fought"),
    ],
)
def test_wrath_undeniable_native_retention_and_replay(
    wrath_definitions: Section02Definitions,
    active: str,
    seed: int,
    expected_roll: int | None,
) -> None:
    battle = _scene(wrath_definitions, seed_label=f"wrath-undeniable:{seed}", active=active)
    session = battle.session
    state = battle.state
    used = False
    retained_model_id = None
    for _ in range(90):
        session.advance_until_decision_or_terminal()
        if state.current_battle_phase is not BattlePhase.FIGHT:
            break
        request = pending(session)
        if WRATH_OPTION in {option.option_id for option in request.options}:
            assert not used
            assert request.actor_id == "owner"
            assert not retained_destructions(state=state)
            checkpoint = session.to_persistence_payload()
            assert (
                LocalGameSession.from_persistence_payload(checkpoint).to_persistence_payload()
                == checkpoint
            )
            session.submit_option(
                request_id=request.request_id,
                result_id=f"{request.request_id}:wrath",
                option_id=WRATH_OPTION,
            )
            used = True
            assert state.command_point_total("owner") == 0
        elif request.decision_type == "select_destruction_reaction":
            assert request.actor_id == "owner"
            record = next(
                r for r in retained_destructions(state=state) if r.request_id == request.request_id
            )
            (source,) = record.eligible_sources
            assert source.source_rule_id == wrath.WRATH_UNDENIABLE_SOURCE_ID
            assert len(request.options) == 2
            boundary = next(
                event
                for event in session.lifecycle.decision_controller.event_log.records
                if event.event_id == record.owner_context["attacks_resolved_event_id"]
            )
            assert boundary.event_type == "attack_sequence_attacks_resolved"
            assert state.battlefield_state is not None
            assert (
                state.battlefield_state.model_placement_or_none(record.model_instance_id)
                == record.placement
            )
            checkpoint = session.to_persistence_payload()
            assert (
                LocalGameSession.from_persistence_payload(checkpoint).to_persistence_payload()
                == checkpoint
            )
            session.submit_option(
                request_id=request.request_id,
                result_id=f"{request.request_id}:wrath",
                option_id=source.source_id,
            )
            if retained_model_id is None:
                retained_model_id = record.model_instance_id
        else:
            _play(battle, request, retained_model_id=retained_model_id)
    else:
        raise AssertionError("Wrath Undeniable Fight did not end")
    assert used
    assert state.battlefield_state is not None
    if active == "opponent":
        assert retained_model_id is not None
        assert retained_model_id in state.battlefield_state.removed_model_ids
        assert any(
            retained_model_id in cast(list[str], attack["model_instance_ids"])
            for attack in events(session, "attack_sequence_models_attacked")
        )
    else:
        assert retained_model_id is None
    assert not retained_destructions(state=state)
    triggers = events(session, "fight_on_death_retention_trigger_resolved")
    assert triggers
    assert len({cast(str, trigger["model_instance_id"]) for trigger in triggers}) == len(triggers)
    rolls: list[int] = []
    for trigger in triggers:
        source_payload = cast(dict[str, JsonValue], trigger["source"])
        assert source_payload["source_rule_id"] == wrath.WRATH_UNDENIABLE_SOURCE_ID
        if active == "opponent":
            assert trigger["applicable"] is True
            roll = cast(dict[str, JsonValue], trigger["trigger_roll"])
            original = cast(dict[str, JsonValue], roll["original_result"])
            (value,) = cast(list[int], original["values"])
            rolls.append(value)
            assert trigger["triggered"] is (value >= 4)
        else:
            assert trigger["applicable"] is False
            assert trigger["trigger_roll"] is None
            assert trigger["triggered"] is False
    if expected_roll is not None:
        assert expected_roll in rolls
    assert not any(
        effect.source_rule_id == wrath.WRATH_UNDENIABLE_SOURCE_ID
        for effect in state.persisting_effects
    )
    replay = ReplayRunner.from_payload(
        session.replay_artifact(artifact_id="wrath-undeniable")
    ).run()
    assert replay.reproduced_exactly, replay
