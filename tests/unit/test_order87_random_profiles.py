from __future__ import annotations

import json
from dataclasses import replace
from typing import cast

import pytest

from warhammer40k_core.core.army_catalog import ArmyCatalog, ArmyCatalogPayload
from warhammer40k_core.core.attributes import Characteristic, CharacteristicError
from warhammer40k_core.core.datasheet import DatasheetDefinition
from warhammer40k_core.core.dice import DiceExpression
from warhammer40k_core.core.random_profile_values import RandomProfileValue
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.phase import BattlePhase


def test_random_model_profile_survives_catalog_loading_without_a_numeric_placeholder() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    sheet = catalog.datasheet_by_id("core-intercessor-like-infantry")
    profile = sheet.model_profiles[0]
    random = RandomProfileValue(
        characteristic=Characteristic.MOVEMENT,
        expression=DiceExpression(2, 6, 1),
        source_id=profile.source_ids[0],
    )
    profile = replace(
        profile,
        characteristics=tuple(
            random if value.characteristic is Characteristic.MOVEMENT else value
            for value in profile.characteristics
        ),
    )
    sheet = replace(sheet, model_profiles=(profile, *sheet.model_profiles[1:]))
    catalog = replace(
        catalog,
        datasheets=tuple(
            sheet if row.datasheet_id == sheet.datasheet_id else row for row in catalog.datasheets
        ),
    )
    loaded = ArmyCatalog.from_payload(
        cast(ArmyCatalogPayload, json.loads(json.dumps(catalog.to_payload())))
    )
    value = (
        loaded.datasheet_by_id(sheet.datasheet_id)
        .model_profiles[0]
        .characteristic(Characteristic.MOVEMENT)
    )
    assert isinstance(value, RandomProfileValue)
    assert value == random
    assert value.to_payload()["expression"] == {"quantity": 2, "sides": 6, "modifier": 1}
    with pytest.raises(CharacteristicError, match="unresolved"):
        _ = value.final


@pytest.mark.parametrize("expression", [DiceExpression(1, 6, -1), DiceExpression(1, 6, -7)])
def test_random_profile_rejects_nonpositive_movement_outcomes(expression: DiceExpression) -> None:
    with pytest.raises(CharacteristicError, match="positive"):
        RandomProfileValue(Characteristic.MOVEMENT, expression, "test:random-profile")


def test_random_profile_requires_source_identity() -> None:
    with pytest.raises(CharacteristicError, match="source_id"):
        RandomProfileValue(Characteristic.MOVEMENT, DiceExpression(1, 6), "")


@pytest.mark.parametrize("characteristic", [Characteristic.WEAPON_SKILL, Characteristic.TOUGHNESS])
def test_random_melee_profiles_use_physical_attack_occurrences(
    characteristic: Characteristic,
) -> None:
    from tests.phase15c_fight_order_helpers import (
        drain_fight_movement_requests,
        fight_lifecycle,
        submit_minimal_melee_declaration,
    )

    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.core.weapon_profiles import RangeProfileKind
    from warhammer40k_core.geometry.pose import Pose

    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    if characteristic is Characteristic.WEAPON_SKILL:
        catalog = replace(
            catalog,
            wargear=tuple(
                replace(
                    item,
                    weapon_profiles=tuple(
                        replace(
                            profile,
                            skill=RandomProfileValue(
                                characteristic,
                                DiceExpression(1, 3, 1),
                                "fixture:order87:melee",
                            ),
                            source_ids=(*profile.source_ids, "fixture:order87:melee"),
                        )
                        if profile.range_profile.kind is RangeProfileKind.MELEE
                        else profile
                        for profile in item.weapon_profiles
                    ),
                )
                for item in catalog.wargear
            ),
        )
    else:
        catalog = replace(
            catalog,
            datasheets=tuple(
                replace(
                    sheet,
                    model_profiles=tuple(
                        replace(
                            profile,
                            characteristics=tuple(
                                RandomProfileValue(
                                    characteristic, DiceExpression(1, 3, 1), profile.source_ids[0]
                                )
                                if value.characteristic is characteristic
                                else value
                                for value in profile.characteristics
                            ),
                        )
                        for profile in sheet.model_profiles
                    ),
                )
                for sheet in catalog.datasheets
            ),
        )
    lifecycle, _ = fight_lifecycle(
        alpha_unit_ids=("attacker",),
        enemy_unit_ids=("defender",),
        origins={"attacker": Pose.at(10, 20), "defender": Pose.at(12, 20)},
        game_id=f"order87-melee-{characteristic.value}",
        catalog=catalog,
        datasheet_id="core-character-leader",
        model_profile_id="core-character-leader",
        model_count=1,
        record_deployment=True,
    )
    session = LocalGameSession(lifecycle)
    status = session.advance_until_decision_or_terminal()
    for step in range(50):
        status = drain_fight_movement_requests(lifecycle, status)
        request = status.decision_request
        assert request is not None
        if request.decision_type == "submit_melee_declaration":
            status = submit_minimal_melee_declaration(
                lifecycle,
                request=request,
                result_id=f"melee-profiles-{step}",
            )
        else:
            completed = any(
                event.event_type == "attack_sequence_completed"
                for event in lifecycle.decision_controller.event_log.records
            )
            if completed:
                break
            option = next(
                option for option in request.options if not option.option_id.startswith("complete")
            )
            status = session.submit_option(
                request_id=request.request_id,
                option_id=option.option_id,
                result_id=f"melee-profiles-{step}",
            )
    else:
        pytest.fail("Random melee sequence did not complete.")
    evaluations = [
        event
        for event in lifecycle.decision_controller.event_log.records
        if event.event_type
        in {"random_weapon_profile_evaluated", "random_profile_values_evaluated"}
    ]
    assert evaluations
    before = lifecycle.decision_controller.event_log.to_payload()
    for viewer in ("player-a", "player-b"):
        session.view(viewer_player_id=viewer)
    assert lifecycle.decision_controller.event_log.to_payload() == before
    checkpoint = session.to_persistence_payload()
    assert (
        LocalGameSession.from_persistence_payload(
            json.loads(json.dumps(checkpoint))
        ).to_persistence_payload()
        == checkpoint
    )


@pytest.mark.parametrize("parameterized", [False, True])
def test_random_reactive_movement_gets_a_fresh_roll_in_the_owners_turn(
    parameterized: bool,
) -> None:
    from tests.normal_move_occurrence_helpers import (
        accept_reaction,
        next_player_action,
        reaction_session,
        request_from,
        submit_path,
    )

    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.engine.replay import ReplayRunner

    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    sheet = catalog.datasheet_by_id("core-intercessor-like-infantry")
    profile = sheet.model_profiles[0]
    random = RandomProfileValue(
        Characteristic.MOVEMENT, DiceExpression(2, 6), profile.source_ids[0]
    )
    sheet = replace(
        sheet,
        model_profiles=(
            replace(
                profile,
                characteristics=tuple(
                    random if value.characteristic is Characteristic.MOVEMENT else value
                    for value in profile.characteristics
                ),
            ),
            *sheet.model_profiles[1:],
        ),
    )
    catalog = replace(
        catalog,
        datasheets=tuple(
            sheet if row.datasheet_id == sheet.datasheet_id else row for row in catalog.datasheets
        ),
    )
    session, unit_id = reaction_session(
        attached=True,
        parameterized=parameterized,
        catalog=catalog,
    )
    status = accept_reaction(session, parameterized=parameterized)
    action = next_player_action(session, status, unit_id)
    records = session.lifecycle.decision_controller.event_log.records
    rolls = [
        event
        for event in records
        if event.event_type == "random_characteristic_rolled"
        and isinstance(event.payload, dict)
        and event.payload.get("characteristic") == "movement"
        and unit_id in str(event.payload.get("scope_id"))
    ]
    assert len(rolls) == 2
    assert rolls[0].payload != rolls[1].payload
    for viewer in ("player-a", "player-b"):
        session.view(viewer_player_id=viewer)
    assert session.lifecycle.decision_controller.event_log.records == records
    proposal = request_from(
        session.submit_option(
            request_id=action.request_id,
            option_id="normal_move",
            result_id="random-own-move",
        )
    )
    submit_path(session, proposal, result_id="random-own-path")
    checkpoint = session.to_persistence_payload()
    assert (
        LocalGameSession.from_persistence_payload(
            json.loads(json.dumps(checkpoint))
        ).to_persistence_payload()
        == checkpoint
    )
    assert (
        ReplayRunner.from_payload(session.replay_artifact(artifact_id="random-reactive-movement"))
        .run()
        .reproduced_exactly
    )


def test_random_movement_is_rolled_at_facade_selection_once_for_the_unit() -> None:
    from tests.phase15c_fight_order_helpers import fight_lifecycle

    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.engine.phase import BattlePhase
    from warhammer40k_core.geometry.pose import Pose

    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    sheet = catalog.datasheet_by_id("core-intercessor-like-infantry")
    profile = sheet.model_profiles[0]
    profile = replace(
        profile,
        characteristics=tuple(
            RandomProfileValue(Characteristic.MOVEMENT, DiceExpression(2, 6), profile.source_ids[0])
            if value.characteristic is Characteristic.MOVEMENT
            else value
            for value in profile.characteristics
        ),
    )
    sheet = replace(sheet, model_profiles=(profile, *sheet.model_profiles[1:]))
    catalog = replace(
        catalog,
        datasheets=tuple(
            sheet if row.datasheet_id == sheet.datasheet_id else row for row in catalog.datasheets
        ),
    )
    lifecycle, _ = fight_lifecycle(
        alpha_unit_ids=("mover",),
        enemy_unit_ids=("target",),
        origins={"mover": Pose.at(10, 20), "target": Pose.at(40, 20)},
        game_id="order87-random-movement",
        catalog=catalog,
        battle_phase=BattlePhase.MOVEMENT,
        record_deployment=True,
    )
    session = LocalGameSession(lifecycle)
    selection = session.advance_until_decision_or_terminal().decision_request
    assert selection is not None
    before = len(lifecycle.decision_controller.event_log.records)
    for player in ("player-a", "player-b"):
        session.view(viewer_player_id=player)
    assert len(lifecycle.decision_controller.event_log.records) == before
    action = session.submit_option(
        request_id=selection.request_id,
        option_id="army-alpha:mover",
        result_id="select-random-mover",
    ).decision_request
    assert action is not None
    assert action.decision_type == "select_movement_action"
    rolls = [
        e
        for e in lifecycle.decision_controller.event_log.records
        if e.event_type == "random_characteristic_rolled"
    ]
    assert len(rolls) == 1
    state = lifecycle.state
    assert state is not None
    army = state.army_definition_for_player("player-a")
    assert army is not None
    values = [
        m.characteristic(Characteristic.MOVEMENT)
        for m in army.unit_by_id("army-alpha:mover").own_models
    ]
    assert all(isinstance(v, RandomProfileValue) for v in values)
    assert len({v.final for v in values}) == 1
    after = len(lifecycle.decision_controller.event_log.records)
    for player in ("player-a", "player-b"):
        session.view(viewer_player_id=player)
    assert len(lifecycle.decision_controller.event_log.records) == after
    checkpoint = session.to_persistence_payload()
    assert (
        LocalGameSession.from_persistence_payload(
            json.loads(json.dumps(checkpoint))
        ).to_persistence_payload()
        == checkpoint
    )
    from warhammer40k_core.engine.replay import ReplayRunner

    assert (
        ReplayRunner.from_payload(session.replay_artifact(artifact_id="random-movement"))
        .run()
        .reproduced_exactly
    )

    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.phase import GameLifecycleError

    for field, forged in (
        ("scope_id", "unknown-selection"),
        ("unit_instance_id", "wrong-unit"),
        ("player_id", "player-b"),
        ("unrecognized", True),
    ):
        tampered = json.loads(json.dumps(lifecycle.to_payload()))
        event = next(
            item
            for item in tampered["decisions"]["event_log"]
            if item["event_type"] == "random_profile_values_evaluated"
        )
        event["payload"][field] = forged
        with pytest.raises(GameLifecycleError):
            GameLifecycle.from_payload(tampered)


def test_mixed_attached_movement_preserves_fixed_values_and_separates_expressions() -> None:
    from tests.phase13b_shooting_declaration_helpers import (
        _attached_enemy_declarations,
        _attached_enemy_unit_specs,
    )
    from tests.phase15c_fight_order_helpers import fight_lifecycle

    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.engine.phase import BattlePhase
    from warhammer40k_core.engine.rules_units import rules_unit_views_for_state
    from warhammer40k_core.geometry.pose import Pose

    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    sheets: list[DatasheetDefinition] = []
    for sheet in catalog.datasheets:
        quantity = {"core-intercessor-like-infantry": 1, "core-character-support": 2}.get(
            sheet.datasheet_id
        )
        if quantity is not None:
            sheet = replace(
                sheet,
                model_profiles=tuple(
                    replace(
                        profile,
                        characteristics=tuple(
                            RandomProfileValue(
                                Characteristic.MOVEMENT,
                                DiceExpression(quantity, 6),
                                profile.source_ids[0],
                            )
                            if v.characteristic is Characteristic.MOVEMENT
                            else v
                            for v in profile.characteristics
                        ),
                    )
                    for profile in sheet.model_profiles
                ),
            )
        sheets.append(sheet)
    catalog = replace(catalog, datasheets=tuple(sheets))
    lifecycle, _ = fight_lifecycle(
        alpha_unit_ids=tuple(row[0] for row in _attached_enemy_unit_specs()),
        enemy_unit_ids=("enemy",),
        alpha_unit_specs={row[0]: (row[1], row[2], row[3]) for row in _attached_enemy_unit_specs()},
        alpha_attachment_declarations=_attached_enemy_declarations(),
        origins={
            "bodyguard-unit": Pose.at(10, 20),
            "leader-unit": Pose.at(10, 21.4),
            "support-unit": Pose.at(11.4, 21.4),
            "enemy": Pose.at(40, 20),
        },
        game_id="order87-mixed",
        catalog=catalog,
        battle_phase=BattlePhase.MOVEMENT,
        record_deployment=True,
    )
    session = LocalGameSession(lifecycle)
    request = session.advance_until_decision_or_terminal().decision_request
    assert request is not None
    state = lifecycle.state
    assert state is not None
    unit = next(
        u for u in rules_unit_views_for_state(state=state) if u.owner_player_id == "player-a"
    )
    session.submit_option(
        request_id=request.request_id,
        option_id=unit.unit_instance_id,
        result_id="mixed-move-selection",
    )
    unit = next(
        u for u in rules_unit_views_for_state(state=state) if u.owner_player_id == "player-a"
    )
    models = unit.alive_models()
    fixed = [
        m.characteristic(Characteristic.MOVEMENT)
        for m in models
        if m.datasheet_id == "core-character-leader"
    ]
    assert fixed
    assert all(v.final == 6 for v in fixed)
    events = [
        e.payload
        for e in lifecycle.decision_controller.event_log.records
        if e.event_type == "random_characteristic_rolled"
    ]
    assert len(events) == 2
    assert isinstance(events[0], dict)
    assert isinstance(events[1], dict)
    assert events[0]["roll_state"] != events[1]["roll_state"]
    one_die = [
        m.characteristic(Characteristic.MOVEMENT)
        for m in models
        if m.datasheet_id == "core-intercessor-like-infantry"
    ]
    assert len(one_die) == 5
    assert len({v.final for v in one_die}) == 1
    checkpoint = session.to_persistence_payload()
    assert (
        LocalGameSession.from_persistence_payload(
            json.loads(json.dumps(checkpoint))
        ).to_persistence_payload()
        == checkpoint
    )


@pytest.mark.parametrize(
    ("characteristic", "torrent_skill"),
    [
        (Characteristic.STRENGTH, False),
        (Characteristic.TOUGHNESS, False),
        (Characteristic.SAVE, False),
        (Characteristic.INVULNERABLE_SAVE, False),
        (Characteristic.BALLISTIC_SKILL, False),
        (Characteristic.ARMOR_PENETRATION, False),
        (Characteristic.BALLISTIC_SKILL, True),
        (Characteristic.RANGE, False),
        (Characteristic.RANGE, True),
    ],
)
def test_random_characteristics_are_evaluated_at_shooting_uses(
    characteristic: Characteristic,
    torrent_skill: bool,
) -> None:
    from tests.phase13b_shooting_declaration_helpers import (
        _catalog_with_extra_bolt_profile,
        _compact_shooting_lifecycle,
        _proposal_from_request,
        _weapon_profile_by_wargear,
    )

    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.core.attributes import CharacteristicValue
    from warhammer40k_core.core.weapon_profiles import AttackProfile, RangeProfile, WeaponKeyword
    from warhammer40k_core.engine.event_log import validate_json_value

    base = _weapon_profile_by_wargear(wargear_id="core-bolt-rifle", weapon_profile_id=None)
    profile = replace(
        base,
        profile_id="order87-random-strength",
        source_ids=("fixture:order87-random-strength",),
        attack_profile=AttackProfile.fixed(2),
        keywords=(WeaponKeyword.TORRENT,),
        abilities=(),
        strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 12),
    )
    field = {
        Characteristic.STRENGTH: "strength",
        Characteristic.BALLISTIC_SKILL: "skill",
        Characteristic.ARMOR_PENETRATION: "armor_penetration",
    }.get(characteristic)
    if field is not None:
        expression = (
            DiceExpression(1, 6, -6)
            if characteristic is Characteristic.ARMOR_PENETRATION
            else DiceExpression(1, 3, 2)
        )
        value = RandomProfileValue(characteristic, expression, "fixture:order87-random-strength")
        profile = replace(
            profile,
            strength=value if field == "strength" else profile.strength,
            skill=value if field == "skill" else profile.skill,
            armor_penetration=value if field == "armor_penetration" else profile.armor_penetration,
            keywords=() if field == "skill" and not torrent_skill else profile.keywords,
        )
    if characteristic is Characteristic.RANGE:
        profile = replace(
            profile,
            range_profile=RangeProfile.random(
                RandomProfileValue(
                    Characteristic.RANGE,
                    DiceExpression(1, 6, 0 if torrent_skill else 24),
                    profile.source_ids[0],
                )
            ),
        )
    catalog = _catalog_with_extra_bolt_profile(profile)
    if characteristic is Characteristic.RANGE and torrent_skill:
        catalog = replace(
            catalog,
            wargear=tuple(
                replace(item, weapon_profiles=(profile,))
                if profile in item.weapon_profiles
                else item
                for item in catalog.wargear
            ),
        )
    if characteristic in (
        Characteristic.TOUGHNESS,
        Characteristic.SAVE,
        Characteristic.INVULNERABLE_SAVE,
    ):
        catalog = replace(
            catalog,
            datasheets=tuple(
                replace(
                    sheet,
                    model_profiles=tuple(
                        replace(
                            model,
                            characteristics=(
                                *(
                                    v
                                    for v in model.characteristics
                                    if v.characteristic is not characteristic
                                ),
                                RandomProfileValue(
                                    characteristic, DiceExpression(1, 3, 2), model.source_ids[0]
                                ),
                            ),
                        )
                        for model in sheet.model_profiles
                    ),
                )
                for sheet in catalog.datasheets
            ),
        )
    lifecycle, units = _compact_shooting_lifecycle(
        alpha_unit_ids=("shooter",),
        enemy_model_count=2,
        game_id="order87-weapon-strength",
        catalog=catalog,
    )
    from warhammer40k_core.engine.lifecycle import GameLifecycle

    lifecycle = GameLifecycle.from_payload(lifecycle.to_payload())
    session = LocalGameSession(lifecycle)
    request = session.advance_until_decision_or_terminal().decision_request
    assert request is not None
    request = session.submit_option(
        request_id=request.request_id,
        option_id=units["shooter"].unit_instance_id,
        result_id="select-shooter",
    ).decision_request
    assert request is not None
    if characteristic is Characteristic.RANGE and torrent_skill:
        assert any(
            event.event_type == "shooting_selection_without_targets"
            for event in lifecycle.decision_controller.event_log.records
        )
        checkpoint = session.to_persistence_payload()
        assert (
            LocalGameSession.from_persistence_payload(
                json.loads(json.dumps(checkpoint))
            ).to_persistence_payload()
            == checkpoint
        )
        return
    if request.decision_type == "select_shooting_type":
        request = session.submit_option(
            request_id=request.request_id,
            option_id=request.options[0].option_id,
            result_id="select-shooting-type",
        ).decision_request
        assert request is not None
    proposal = _proposal_from_request(
        request=request,
        target_unit_id=units["enemy"].unit_instance_id,
        weapon_profile_id=profile.profile_id,
    )
    session.submit_parameterized_payload(
        request_id=request.request_id,
        payload=validate_json_value(proposal.to_payload()),
        result_id="declare-shots",
    )
    events = [
        e.payload
        for e in lifecycle.decision_controller.event_log.records
        if e.event_type == "random_weapon_profile_evaluated"
    ]
    if characteristic is Characteristic.RANGE:
        range_events = [
            e
            for e in lifecycle.decision_controller.event_log.records
            if e.event_type == "random_weapon_range_evaluated"
        ]
        assert len(range_events) == 1
        assert events == []
    elif torrent_skill:
        assert events == []
    elif characteristic is Characteristic.TOUGHNESS:
        rolls = [
            e
            for e in lifecycle.decision_controller.event_log.records
            if e.event_type == "random_characteristic_rolled"
        ]
        assert len(rolls) == 4
    elif characteristic in (Characteristic.SAVE, Characteristic.INVULNERABLE_SAVE):
        rolls = [
            e
            for e in lifecycle.decision_controller.event_log.records
            if e.event_type == "random_characteristic_rolled"
        ]
        assert len(rolls) == 2
    elif characteristic is Characteristic.ARMOR_PENETRATION:
        assert 0 < len(events) <= 2
    else:
        assert len(events) == 2
    assert all(isinstance(e, dict) and e["weapon_profile_id"] == profile.profile_id for e in events)
    dice = [
        e for e in lifecycle.decision_controller.event_log.records if e.event_type == "dice_rolled"
    ]
    assert len({cast(dict[str, object], e.payload)["roll_id"] for e in dice}) == len(dice)

    checkpoint = session.to_persistence_payload()
    assert (
        LocalGameSession.from_persistence_payload(
            json.loads(json.dumps(checkpoint))
        ).to_persistence_payload()
        == checkpoint
    )


def test_random_leadership_is_evaluated_per_living_model_at_command_test() -> None:
    from tests.phase11c_command_phase_helpers import destroy_models_with_recorded_mortal_wounds
    from tests.phase15c_fight_order_helpers import fight_lifecycle

    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.engine.phase import BattlePhase
    from warhammer40k_core.geometry.pose import Pose

    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    catalog = replace(
        catalog,
        datasheets=tuple(
            replace(
                sheet,
                model_profiles=tuple(
                    replace(
                        profile,
                        characteristics=tuple(
                            RandomProfileValue(
                                Characteristic.LEADERSHIP,
                                DiceExpression(1, 6, 3),
                                profile.source_ids[0],
                            )
                            if value.characteristic is Characteristic.LEADERSHIP
                            else value
                            for value in profile.characteristics
                        ),
                    )
                    for profile in sheet.model_profiles
                ),
            )
            for sheet in catalog.datasheets
        ),
    )
    lifecycle, _ = fight_lifecycle(
        alpha_unit_ids=("tester",),
        enemy_unit_ids=("enemy",),
        origins={"tester": Pose.at(10, 20), "enemy": Pose.at(40, 20)},
        game_id="order87-random-leadership",
        catalog=catalog,
        battle_phase=BattlePhase.COMMAND,
        record_deployment=True,
    )
    assert lifecycle.state is not None
    army = lifecycle.state.army_definition_for_player("player-a")
    assert army is not None
    destroy_models_with_recorded_mortal_wounds(
        state=lifecycle.state,
        decisions=lifecycle.decision_controller,
        unit_instance_id="army-alpha:tester",
        model_instance_ids=tuple(
            m.model_instance_id for m in army.unit_by_id("army-alpha:tester").own_models[:3]
        ),
        application_id="order87-preexisting-casualties",
        destroying_player_id="player-b",
    )
    session = LocalGameSession(lifecycle)
    status = session.advance_until_decision_or_terminal()
    from warhammer40k_core.engine.stratagems import stratagem_decline_payload

    for step in range(10):
        if any(
            e.event_type == "battle_shock_test_requested"
            for e in lifecycle.decision_controller.event_log.records
        ):
            break
        pending = status.decision_request
        assert pending is not None
        if pending.decision_type == "submit_stratagem_target_proposal":
            status = session.submit_parameterized_payload(
                request_id=pending.request_id,
                result_id=f"command-choice-{step}",
                payload=stratagem_decline_payload(),
            )
        else:
            status = session.submit_option(
                request_id=pending.request_id,
                result_id=f"command-choice-{step}",
                option_id=pending.options[0].option_id,
            )
    rolls = [
        e.payload
        for e in lifecycle.decision_controller.event_log.records
        if e.event_type == "random_characteristic_rolled"
    ]
    assert len(rolls) == 2, status.decision_request
    assert all(isinstance(row, dict) and row["characteristic"] == "leadership" for row in rolls)
    requests = [
        e.payload
        for e in lifecycle.decision_controller.event_log.records
        if e.event_type == "battle_shock_test_requested"
    ]
    assert len(requests) == 1
    payload = requests[0]
    assert isinstance(payload, dict)
    request = payload["battle_shock_test_request"]
    assert isinstance(request, dict)
    assert request["leadership_target"] == min(cast(dict[str, int], row)["value"] for row in rolls)

    from warhammer40k_core.engine.lifecycle import GameLifecycle

    checkpoint = lifecycle.to_payload()
    assert GameLifecycle.from_payload(json.loads(json.dumps(checkpoint))).to_payload() == checkpoint


def test_random_wounds_initialize_at_engine_setup_and_restore_without_rerolling() -> None:
    from tests.phase11c_command_phase_helpers import phase11c_config

    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.engine.army_mustering import muster_army
    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.unit_factory import UnitFactoryError

    config = phase11c_config(game_id="order87-random-wounds")
    catalog = config.army_catalog
    catalog = replace(
        catalog,
        datasheets=tuple(
            replace(
                sheet,
                model_profiles=tuple(
                    replace(
                        profile,
                        characteristics=tuple(
                            RandomProfileValue(
                                Characteristic.WOUNDS,
                                DiceExpression(1, 6, 2),
                                profile.source_ids[0],
                            )
                            if value.characteristic is Characteristic.WOUNDS
                            else value
                            for value in profile.characteristics
                        ),
                    )
                    for profile in sheet.model_profiles
                ),
            )
            for sheet in catalog.datasheets
        ),
    )
    config = replace(config, army_catalog=catalog)
    roster = muster_army(catalog=catalog, request=config.army_muster_requests[0])
    model = roster.units[0].own_models[0]
    assert model.starting_wounds is None
    assert model.wounds_remaining is None
    with pytest.raises(UnitFactoryError, match="not been initialized"):
        _ = model.is_alive
    lifecycle = GameLifecycle()
    session = LocalGameSession(lifecycle)
    session.start(config)
    session.advance_until_decision_or_terminal()
    state = lifecycle.state
    assert state is not None
    models = [m for a in state.army_definitions for u in a.units for m in u.own_models]
    assert models
    assert all(3 <= m.initial_wounds <= 8 for m in models)
    assert all(m.current_wounds == m.initial_wounds for m in models)
    rolls = [
        e
        for e in lifecycle.decision_controller.event_log.records
        if e.event_type == "random_characteristic_rolled"
    ]
    assert len(rolls) == len(models)
    checkpoint = session.to_persistence_payload()
    assert (
        LocalGameSession.from_persistence_payload(
            json.loads(json.dumps(checkpoint))
        ).to_persistence_payload()
        == checkpoint
    )
    assert len(
        [
            e
            for e in lifecycle.decision_controller.event_log.records
            if e.event_type == "random_characteristic_rolled"
        ]
    ) == len(models)


def _random_objective_control_lifecycle(
    *,
    battle_phase: BattlePhase = BattlePhase.CHARGE,
) -> GameLifecycle:
    from tests.phase15c_fight_order_helpers import fight_lifecycle, mission_setup

    from warhammer40k_core.geometry.pose import Pose

    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    catalog = replace(
        catalog,
        datasheets=tuple(
            replace(
                sheet,
                model_profiles=tuple(
                    replace(
                        profile,
                        characteristics=tuple(
                            RandomProfileValue(
                                Characteristic.OBJECTIVE_CONTROL,
                                DiceExpression(1, 6),
                                profile.source_ids[0],
                            )
                            if value.characteristic is Characteristic.OBJECTIVE_CONTROL
                            else value
                            for value in profile.characteristics
                        ),
                    )
                    for profile in sheet.model_profiles
                ),
            )
            for sheet in catalog.datasheets
        ),
    )
    marker = mission_setup().objective_markers[0]
    lifecycle, _ = fight_lifecycle(
        alpha_unit_ids=("holder",),
        enemy_unit_ids=("enemy",),
        origins={
            "holder": Pose.at(marker.x_inches + 2, marker.y_inches),
            "enemy": Pose.at(marker.x_inches + 12, marker.y_inches),
        },
        game_id="order87-objective-control",
        catalog=catalog,
        battle_phase=battle_phase,
        record_deployment=True,
    )
    return lifecycle


def test_random_objective_control_is_frozen_per_boundary_and_restores_historical_values() -> None:
    from warhammer40k_core.adapters.local_session import LocalGameSession

    lifecycle = _random_objective_control_lifecycle()
    session = LocalGameSession(lifecycle)
    request = session.advance_until_decision_or_terminal().decision_request
    assert request is not None
    assert any(option.option_id == "complete_charge_phase" for option in request.options), (
        request.decision_type,
        [option.option_id for option in request.options],
    )
    session.submit_option(
        request_id=request.request_id,
        option_id="complete_charge_phase",
        result_id="complete-random-oc-charge",
    )
    state = lifecycle.state
    assert state is not None
    assert state.objective_control_records
    rolls = [
        event
        for event in lifecycle.decision_controller.event_log.records
        if event.event_type == "random_profile_values_evaluated"
        and isinstance(event.payload, dict)
        and str(event.payload["scope_id"]).startswith("objective-control:")
    ]
    assert len(rolls) >= 2
    before = lifecycle.decision_controller.event_log.to_payload()
    session.view(viewer_player_id="player-a")
    session.view(viewer_player_id="player-b")
    assert lifecycle.decision_controller.event_log.to_payload() == before
    checkpoint = session.to_persistence_payload()
    assert (
        LocalGameSession.from_persistence_payload(
            json.loads(json.dumps(checkpoint))
        ).to_persistence_payload()
        == checkpoint
    )


def test_range_modifier_keeps_the_physical_roll_and_intrinsic_offset() -> None:
    from warhammer40k_core.core.weapon_profiles import RangeProfile
    from warhammer40k_core.engine.profile_modifiers import range_with_delta

    source = RandomProfileValue(Characteristic.RANGE, DiceExpression(1, 6, 12), "source:weapon")
    unresolved = range_with_delta(
        RangeProfile.random(source), 6, source_id="source:range-bonus", target_id="model:bearer"
    )
    assert unresolved.distance_inches is None
    assert unresolved.random_value is not None
    assert unresolved.random_value.expression == source.expression
    selected = source.evaluate(
        raw=16, evaluation_id="selection:weapon-range", target_id="model:bearer"
    )
    modified = range_with_delta(
        RangeProfile.random(selected), 6, source_id="source:range-bonus", target_id="model:bearer"
    )
    assert modified.distance_inches == 22
    assert modified.random_value is not None
    assert modified.random_value.raw == 16
    assert modified.random_value.evaluation_id == selected.evaluation_id
    assert (
        range_with_delta(modified, 6, source_id="source:range-bonus", target_id="model:bearer")
        == modified
    )


def test_battle_shock_suppresses_random_objective_control_without_rolling() -> None:
    from warhammer40k_core.engine.objective_control import (
        ObjectiveControlContext,
        ObjectiveControlTiming,
    )
    from warhammer40k_core.engine.random_objective_control import evaluate_objective_control
    from warhammer40k_core.engine.rules_units import rules_unit_views_for_state

    lifecycle = _random_objective_control_lifecycle()
    state = lifecycle.state
    assert state is not None
    assert state.current_battle_phase is not None
    context = replace(
        ObjectiveControlContext.from_game_state(
            state,
            timing=ObjectiveControlTiming.PHASE_END,
            phase=state.current_battle_phase,
            ruleset_descriptor=state.runtime_ruleset_descriptor(),
        ),
        state=None,
        battle_shocked_unit_ids=tuple(
            unit.unit_instance_id for unit in rules_unit_views_for_state(state=state)
        ),
    )
    before = lifecycle.decision_controller.event_log.to_payload()
    control = evaluate_objective_control(context, decisions=None, scope_id="suppressed-oc")
    contributors = [row for result in control.results for row in result.contributors]
    assert contributors
    assert all(
        row.objective_control is None and row.effective_objective_control == 0
        for row in contributors
    )
    assert lifecycle.decision_controller.event_log.to_payload() == before


def test_random_objective_control_action_options_are_read_only_after_evaluation() -> None:
    from warhammer40k_core.adapters.local_session import LocalGameSession

    lifecycle = _random_objective_control_lifecycle(battle_phase=BattlePhase.SHOOTING)
    from warhammer40k_core.engine.game_state import SecondaryMissionChoice, SecondaryMissionMode
    from warhammer40k_core.engine.scoring import SecondaryMissionCardState

    state = lifecycle.state
    assert state is not None
    state.secondary_mission_choices = [
        SecondaryMissionChoice(
            player_id="player-a",
            mode=SecondaryMissionMode.TACTICAL,
            fixed_mission_ids=(),
        )
        if choice.player_id == "player-a"
        else choice
        for choice in state.secondary_mission_choices
    ]
    state.secondary_mission_card_states = [
        card for card in state.secondary_mission_card_states if card.player_id != "player-a"
    ] + [
        SecondaryMissionCardState.active_tactical(
            player_id="player-a",
            secondary_mission_id="cleanse",
            battle_round=1,
            source_result_id="random-oc-held-cleanse",
        )
    ]
    state.secondary_mission_card_states.sort(
        key=lambda card: (card.player_id, card.secondary_mission_id)
    )
    session = LocalGameSession(lifecycle)
    request = session.advance_until_decision_or_terminal().decision_request
    assert request is not None
    assert request.decision_type == "start_mission_action", request
    events = lifecycle.decision_controller.event_log.records
    assert any(
        event.event_type == "random_profile_values_evaluated"
        and isinstance(event.payload, dict)
        and str(event.payload["scope_id"]).startswith("mission-action-options:")
        for event in events
    )
    before_restore = lifecycle.to_payload()
    _assert_action_profile_scope_tamper_rejected(lifecycle)
    after_restore = GameLifecycle.from_payload(before_restore).to_payload()
    assert after_restore == before_restore
    checkpoint = session.to_persistence_payload()
    assert (
        LocalGameSession.from_persistence_payload(
            json.loads(json.dumps(checkpoint))
        ).to_persistence_payload()
        == checkpoint
    )
    for player in ("player-a", "player-b"):
        session.view(viewer_player_id=player)
    assert lifecycle.decision_controller.event_log.records == events
    option = next(option for option in request.options if option.option_id.startswith("start:"))
    status = session.submit_option(
        request_id=request.request_id, option_id=option.option_id, result_id="random-oc-action"
    )
    assert lifecycle.state is not None
    assert lifecycle.state.mission_action_states, status
    checkpoint = session.to_persistence_payload()
    assert GameLifecycle.from_payload(lifecycle.to_payload()).to_payload() == lifecycle.to_payload()
    assert (
        LocalGameSession.from_persistence_payload(
            json.loads(json.dumps(checkpoint))
        ).to_persistence_payload()
        == checkpoint
    )


def test_movement_prepares_random_oc_before_mid_phase_control_queries() -> None:
    from tests.normal_move_occurrence_helpers import request_from, submit_path
    from tests.phase15c_fight_order_helpers import fight_lifecycle, mission_setup

    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_daemons import (
        army_rule,
    )
    from warhammer40k_core.engine.phase import BattlePhase
    from warhammer40k_core.geometry.pose import Pose

    base = _random_objective_control_lifecycle()
    assert base.config is not None
    marker = mission_setup().objective_markers[0]
    lifecycle, _ = fight_lifecycle(
        alpha_unit_ids=("holder", "other"),
        enemy_unit_ids=("enemy",),
        origins={
            "holder": Pose.at(marker.x_inches - 6.1, marker.y_inches),
            "other": Pose.at(70, 50),
            "enemy": Pose.at(50, 50),
        },
        game_id="review-oc-after-move",
        catalog=base.config.army_catalog,
        battle_phase=BattlePhase.MOVEMENT,
        model_count=1,
        datasheet_id="core-character-leader",
        model_profile_id="core-character-leader",
        record_deployment=True,
    )
    session = LocalGameSession(lifecycle)
    request = request_from(session.advance_until_decision_or_terminal())
    request = request_from(
        session.submit_option(
            request_id=request.request_id,
            option_id="army-alpha:holder",
            result_id="review-select-mover",
        )
    )
    request = request_from(
        session.submit_option(
            request_id=request.request_id, option_id="normal_move", result_id="review-select-normal"
        )
    )
    status = submit_path(session, request, result_id="review-move-to-objective", dx=4)
    assert lifecycle.state is not None
    assert status.decision_request is not None
    assert lifecycle.state.current_battle_phase is BattlePhase.MOVEMENT
    assert status.decision_request.decision_type == "select_movement_unit"
    events = lifecycle.decision_controller.event_log.records
    assert any(e.event_type == "random_profile_values_evaluated" for e in events)
    army_rule.shadow_regions_for_player(state=lifecycle.state, player_id="player-a")
    for viewer in ("player-a", "player-b"):
        session.view(viewer_player_id=viewer)
    assert lifecycle.decision_controller.event_log.records == events
    checkpoint = lifecycle.to_payload()
    assert GameLifecycle.from_payload(checkpoint).to_payload() == checkpoint


def _assert_action_profile_scope_tamper_rejected(lifecycle: GameLifecycle) -> None:
    from collections.abc import Iterator

    from warhammer40k_core.core.descriptor_hash import canonical_payload_sha256
    from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
    from warhammer40k_core.engine.phase import GameLifecycleError

    state = lifecycle.state
    assert state is not None
    old = next(
        str(event.payload["scope_id"])
        for event in lifecycle.decision_controller.event_log.records
        if event.event_type == "random_profile_values_evaluated"
        and isinstance(event.payload, dict)
        and str(event.payload["scope_id"]).startswith("mission-action-options:")
    )
    new = f"mission-action-options:decision-request-{state.decision_request_count + 1:06d}"
    assert old != new
    payload = validate_json_value(json.loads(json.dumps(lifecycle.to_payload()).replace(old, new)))

    def rows(value: JsonValue) -> Iterator[dict[str, JsonValue]]:
        if isinstance(value, dict):
            yield value
            for child in value.values():
                yield from rows(child)
        elif isinstance(value, list):
            for child in value:
                yield from rows(child)

    for identity, hash_key, content_key in (
        ("checkpoint_id", "checkpoint_hash", "model_states"),
        ("authority_id", "authority_hash", "boundary_checkpoint"),
    ):
        replacements: dict[str, str] = {}
        for row in rows(payload):
            if hash_key in row and content_key in row:
                replacements[str(row[hash_key])] = canonical_payload_sha256(
                    {key: value for key, value in row.items() if key not in {identity, hash_key}}
                )
        serialized = json.dumps(payload)
        for before, after in replacements.items():
            serialized = serialized.replace(before, after)
        payload = validate_json_value(json.loads(serialized))
    with pytest.raises(GameLifecycleError, match="Random OC occurrence"):
        GameLifecycle.from_payload(json.loads(json.dumps(payload)))
