"""Native shooting and Fall Back through the shared source-bound Fortification clause."""

from dataclasses import replace
from typing import cast

import pytest

from tests.setup_completion_helpers import record_primary_turn_start_evidence_for_fixture
from tests.support.faction_batch01 import ELDRAD, RANGERS, anchor, locate, scene, selection
from tests.support.faction_batch01 import faction_definitions as faction_definitions
from tests.support.fortification_fixtures import GNARLMAW, SKULL_ALTAR, with_fortification
from tests.support.section02_fixtures import Section02Definitions
from tests.support.section03_fixtures import grid, native_state, placement
from tests.support.section03_session import movement_session
from tests.support.section04_fixtures import choose as choose_shooting
from tests.support.section04_fixtures import finish_attacks, shooting_payload, weapon_rows
from tests.support.section09_fixtures import (
    add_unit,
    anchor_hazard_scene,
    attach_mission,
    choose,
    events,
    finish_hazard_choices,
    propose,
    select,
)
from tests.support.section09_fixtures import section09_definitions as section09_definitions
from tests.support.section10_fixtures import (
    AVENGERS,
    LORD,
    accepted_pools,
    assert_valid,
    declaration_request,
)
from tests.support.section11_fixtures import begin
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.ability_catalog import catalog_ability_records_from_catalog
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.list_validation import UnitMusterSelection
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatus, LifecycleStatusKind
from warhammer40k_core.engine.phases.movement import DesperateEscapeRoll, DesperateEscapeRollPayload
from warhammer40k_core.engine.phases.movement_handler import MovementPhaseHandler
from warhammer40k_core.engine.shooting_targets import FORTIFICATION_ENGAGEMENT_RULE_ID
from warhammer40k_core.engine.unit_state import StartingStrengthRecord
from warhammer40k_core.geometry.pose import Pose


@pytest.mark.parametrize(
    ("source", "mixed", "crosses", "shocked", "forced", "hazard_count"),
    [
        (GNARLMAW, False, True, True, False, 1),
        (GNARLMAW, False, False, True, False, 0),
        (GNARLMAW, True, True, True, False, 2),
        (GNARLMAW, False, True, False, False, 2),
        (SKULL_ALTAR, False, True, True, False, 1),
        (None, False, True, True, False, 2),
        (GNARLMAW, False, True, True, True, 2),
    ],
)
def test_fortification_fall_back_hazards_follow_each_native_path(
    section09_definitions: Section02Definitions,
    source: str | None,
    mixed: bool,
    crosses: bool,
    shocked: bool,
    forced: bool,
    hazard_count: int,
) -> None:
    provider_sheet = "000004078"  # Known round-base fixture, not a Fortification sculpt.
    # The separate force rule is taken from Bloodletters and attached only in
    # the coexistence control to the borrowed geometry fixture.
    additional_abilities = (
        tuple(
            ability
            for ability in section09_definitions.unit("000001114").datasheet_abilities
            if ability.ability_id == "000001114:bane-of-cowards"
        )
        if forced
        else ()
    )
    assert len(additional_abilities) == int(forced)
    d = with_fortification(
        section09_definitions,
        provider_sheet=provider_sheet,
        fortification_sheet=source,
        additional_abilities=additional_abilities,
    )
    unit = d.unit("000004090")
    provider = d.unit(provider_sheet, army_id="enemy", identity="fortification")
    starts = (Pose.at(10, 10), Pose.at(13, 10))
    state = native_state(d, unit, starts, enemy=provider, enemy_poses=(Pose.at(10, 12.4),))
    if mixed:
        enemy = d.unit("000004090", army_id="enemy", identity="infantry")
        army = state.army_definitions[-1]
        assert army.player_id == "opponent"
        state.army_definitions[-1] = replace(army, units=(*army.units, enemy))
        state.starting_strength_records.append(
            StartingStrengthRecord.from_unit(player_id=army.player_id, unit=enemy)
        )
        assert state.battlefield_state is not None
        state.replace_battlefield_state(
            replace(
                state.battlefield_state,
                placed_armies=tuple(
                    replace(
                        placed,
                        unit_placements=(
                            *placed.unit_placements,
                            placement(enemy, (Pose.at(13, 7.5), Pose.at(15.5, 7.5)), enemy=True),
                        ),
                    )
                    if placed.army_id == army.army_id
                    else placed
                    for placed in state.battlefield_state.placed_armies
                ),
            )
        )
    attach_mission(state)
    add_unit(state, d.unit("000004090", identity="spare"), (Pose.at(10, 30), Pose.at(12.5, 30)))
    if shocked:
        state.battle_shocked_unit_ids.append(unit.unit_instance_id)
    session = movement_session(d, state)
    if forced:
        config = session.lifecycle.config
        index = AbilityCatalogIndex.from_records(
            catalog_ability_records_from_catalog(config.army_catalog)
        )
        handler = MovementPhaseHandler(
            ruleset_descriptor=config.ruleset_descriptor,
            army_catalog=config.army_catalog,
            ability_indexes_by_player_id={"owner": index, "opponent": index},
        )
        session = LocalGameSession(
            GameLifecycle(state=state, _config=config, _movement_phase_handler=handler)
        )
        record_primary_turn_start_evidence_for_fixture(
            state, decisions=session.lifecycle.decision_controller
        )

    # The retained voluntary mode is still mandatory for the already-shocked unit.
    action = select(session, unit)
    assert any(option.option_id == "fall_back:ordered_retreat" for option in action.options) is (
        not shocked
    )
    anchor_hazard_scene(session)
    request = choose(session, action, "fall_back:desperate_escape")
    end_y = 17 if crosses else 6
    status = propose(session, request, unit, (Pose.at(10, end_y), Pose.at(13, end_y)))
    assert status.status_kind is not LifecycleStatusKind.INVALID, status
    first, second = unit.own_model_ids()
    rolls = [
        DesperateEscapeRoll.from_payload(
            cast(DesperateEscapeRollPayload, event["desperate_escape_roll"])
        )
        for event in events(session, "desperate_escape_roll_resolved")
    ]
    assert (
        tuple(roll.requirement.model_instance_id for roll in rolls)
        == (first, second)[:hazard_count]
    )
    if crosses:
        assert rolls[0].requirement.enemy_model_ids == provider.own_model_ids()
        assert "enemy_model_overflight" in rolls[0].requirement.reasons
    if hazard_count == 2:
        assert rolls[1].requirement.enemy_model_ids == ()
        assert ("battle_shocked" in rolls[1].requirement.reasons) is (shocked and not forced)
        if forced:
            assert rolls[1].requirement.reasons == ("forced_by_rule",)

    if forced:
        # This checkpoint supplies an already-shocked unit. The forced test and
        # both hazard rolls must resolve before the pending consequence choice.
        types = [e.event_type for e in session.lifecycle.decision_controller.event_log.records]
        forced_test = types.index("forced_desperate_escape_battle_shock_resolved")
        assert all(
            index < forced_test
            for index, kind in enumerate(types)
            if kind == "desperate_escape_roll_resolved"
        )
        assert "movement_activation_completed" not in types
        assert status.decision_request is not None
        assert status.decision_request.decision_type == "select_mortal_wound_model"
        return
    finish_hazard_choices(session, status)
    (completed,) = events(session, "movement_activation_completed")
    expected_exempt = (
        [second]
        if hazard_count == 1 or forced
        else ([first, second] if hazard_count == 0 else None)
    )
    assert completed.get("fortification_desperate_escape_exempt_model_ids") == expected_exempt
    types = [e.event_type for e in session.lifecycle.decision_controller.event_log.records]
    assert types.count("desperate_escape_battle_shock_resolved") == int(not shocked)
    if not shocked:
        assert (
            types.index("desperate_escape_roll_resolved")
            < types.index("fall_back_move_applied")
            < types.index("desperate_escape_battle_shock_resolved")
            < types.index("movement_activation_completed")
        )


@pytest.mark.parametrize(
    ("source", "mixed", "weapon", "expected_modifier"),
    [
        (GNARLMAW, False, "avenger-shuriken-catapult", -1),
        (GNARLMAW, False, "shuriken-pistol", 0),
        (GNARLMAW, True, "avenger-shuriken-catapult", None),
        (GNARLMAW, True, "shuriken-pistol", None),
        (SKULL_ALTAR, False, "avenger-shuriken-catapult", -1),
        (None, False, "avenger-shuriken-catapult", None),
    ],
)
def test_fortification_engagement_through_normal_shooting(
    faction_definitions: Section02Definitions,
    source: str | None,
    mixed: bool,
    weapon: str,
    expected_modifier: int | None,
) -> None:
    # The descriptor is the source under test. Eldrad supplies known test
    # geometry and does not represent either sculpt or its datasheet loadout.
    d = with_fortification(faction_definitions, provider_sheet=ELDRAD, fortification_sheet=source)
    shooting_sheet = RANGERS if weapon == "shuriken-pistol" else AVENGERS
    friendly: tuple[UnitMusterSelection, ...] = (
        selection(d, shooting_sheet, "shooter"),
        selection(d, ELDRAD, "fortification"),
    )
    if mixed:
        friendly = (*friendly, selection(d, AVENGERS, "infantry"))
    battle = scene(
        d,
        friendly,
        (selection(d, LORD, "engaged"), selection(d, LORD, "unengaged")),
        phase=BattlePhase.SHOOTING,
        seed="fortification-normal-shooting",
    )
    shooter = battle.units["own:shooter"]
    locate(battle, shooter.unit_instance_id, grid(shooter, 11, 20))
    locate(battle, "own:fortification", (Pose.at(20, 22),))
    locate(battle, "foe:engaged", (Pose.at(20, 20),))
    locate(battle, "foe:unengaged", (Pose.at(20, 26),))
    if mixed:
        locate(battle, "own:infantry", grid(battle.units["own:infantry"], 20, 15.8))
    anchor(battle)

    session = battle.session
    request = begin(session)
    if request.decision_type == "start_mission_action":
        choose_shooting(session, request, "continue_to_shooting")
    request = declaration_request(session, shooter, "normal")
    row = next(r for r in weapon_rows(request) if r["wargear_id"] == f"{shooting_sheet}:{weapon}")
    if expected_modifier is None:
        before = session.lifecycle.to_payload()
        result = _submit_native_shot(session, request, (row,), "foe:engaged")
        assert result.status_kind is LifecycleStatusKind.INVALID
        assert session.lifecycle.to_payload() == before
        assert_valid(_submit_native_shot(session, request, (row,), "foe:unengaged"))
        return

    if weapon == "shuriken-pistol":
        rifle = next(
            candidate
            for candidate in weapon_rows(request)
            if candidate["wargear_id"] == f"{RANGERS}:long-rifle"
            and candidate["model_instance_id"] == row["model_instance_id"]
        )
        before = session.lifecycle.to_payload()
        mixed_loadout = _submit_native_shot(session, request, (row, rifle), "foe:engaged")
        assert mixed_loadout.status_kind is LifecycleStatusKind.INVALID
        assert "mixed_close_quarters_non_close_quarters_declaration" in str(mixed_loadout.payload)
        assert session.lifecycle.to_payload() == before

    assert_valid(_submit_native_shot(session, request, (row,), "foe:engaged"))
    (pool,) = accepted_pools(session)
    assert pool["hit_roll_modifier"] == expected_modifier
    assert isinstance(pool["targeting_rule_ids"], list)
    assert (FORTIFICATION_ENGAGEMENT_RULE_ID in pool["targeting_rule_ids"]) is (
        expected_modifier == -1
    )
    finish_attacks(session)
    hit_rolls = [
        cast(dict[str, JsonValue], event["payload"])
        for event in events(session, "attack_sequence_step")
        if event["step"] == "hit"
    ]
    assert hit_rolls
    assert all(roll["modifier"] == expected_modifier for roll in hit_rolls)
    assert all(roll["capped_modifier"] == expected_modifier for roll in hit_rolls)


def _submit_native_shot(
    session: LocalGameSession,
    request: DecisionRequest,
    weapons: tuple[dict[str, JsonValue], ...],
    target: str,
) -> LifecycleStatus:
    payload = shooting_payload(request, list(weapons), (target,) * len(weapons))
    assert isinstance(payload, dict)
    declarations = cast(list[dict[str, JsonValue]], payload["declarations"])
    assert isinstance(request.payload, dict)
    proposal = cast(dict[str, JsonValue], request.payload["proposal_request"])
    candidates = cast(list[dict[str, JsonValue]], proposal["target_candidates"])
    for declaration, weapon in zip(declarations, weapons, strict=True):
        candidate = next(
            row
            for row in candidates
            if row["target_unit_instance_id"] == target
            and row["weapon_instance_id"] == weapon["weapon_instance_id"]
            and row["weapon_profile_id"] == weapon["weapon_profile_id"]
        )
        declaration["selected_weapon_ability_ids"] = [
            cast(list[dict[str, JsonValue]], choice["options"])[0]["option_id"]
            for choice in cast(
                list[dict[str, JsonValue]], candidate["required_weapon_ability_selections"]
            )
        ]
    return session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id=f"fortification:shoot:{target}:{len(weapons)}",
        payload=payload,
    )
