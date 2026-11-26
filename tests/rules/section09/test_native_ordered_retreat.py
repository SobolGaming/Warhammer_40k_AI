"""Native Bloodletters force ordinary Fall Back through Battle-shock and its outcome."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest
from tools.generate_ability_support_matrix import (
    _ability_support_catalog_package,  # pyright: ignore[reportPrivateUsage]
)

from tests.daemons_native_source_helpers import SELECTED
from tests.support.blood_legion import (
    BLOODLETTERS_HEIGHT_OVERRIDES,
    DETACHMENTS,
    blood_legion_definitions,
    identities,
)
from tests.support.faction_batch01 import Scene, anchor, events, locate, request, scene, selection
from tests.support.section02_fixtures import Section02Definitions
from tests.support.section03_fixtures import grid
from tests.support.section09_fixtures import propose
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.detachment import DetachmentDefinition, StratagemDefinition
from warhammer40k_core.core.model_geometry_catalog import GeometrySourceUnits
from warhammer40k_core.engine.battle_shock import BattleShockResult, BattleShockResultPayload
from warhammer40k_core.engine.battle_shock_resolution import BattleShockResolutionResult
from warhammer40k_core.engine.command_points import CommandPointGainStatus, CommandPointSourceKind
from warhammer40k_core.engine.damage_allocation import (
    MortalWoundApplication,
    MortalWoundApplicationPayload,
)
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.list_validation import AttachmentDeclaration
from warhammer40k_core.engine.mortal_wound_model_allocation import mortal_wound_resolution_progress
from warhammer40k_core.engine.movement_proposals import MovementProposalRequest
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlContext,
    ObjectiveControlTiming,
    resolve_objective_control,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.replay import ReplayRunner
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.stratagems import (
    StratagemEligibilityContext,
    request_stratagem_use_from_index,
)
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules import wahapedia_bridge
from warhammer40k_core.rules.catalog_package import CanonicalCatalogPackage
from warhammer40k_core.rules.wahapedia_bridge import ModelHeightOverride
from warhammer40k_core.rules.wahapedia_schema import NormalizedSourceRow

BLOODLETTERS = "000001114"
SPAWN = "000004090"
DAEMON_PRINCE = "000004086"
LORD = "000004078"
SUBJECT = "own:retreat"
FORCER = "foe:letters"
SPARE = "own:spare"
ORDINARY = "fall_back:ordered_retreat"
TERROR_APPLIED = "chaos_daemons_daemonic_terror_mortal_wounds_applied"

WALKER_DETACHMENTS = {"orks": "more-dakka", "chaos-daemons": "blood-legion"}
BOYZ = "000000016"
DEFF_DREAD = "000000040"
WALKER = "own:dread"
HUGE_SHOW_OFFS = "000009992004"


@pytest.fixture(scope="module")
def retreat_definitions(selected_army_source_index: Path | None) -> Section02Definitions:
    package = _ability_support_catalog_package(
        datasheet_ids=(*SELECTED, "000004080", SPAWN, DAEMON_PRINCE, LORD),
        source_index_dir=selected_army_source_index,
    )
    return blood_legion_definitions(Section02Definitions(package, 0.0))


def _restore(session: LocalGameSession) -> LocalGameSession:
    payload = json.loads(json.dumps(session.to_persistence_payload()))
    restored = LocalGameSession.from_persistence_payload(payload)
    assert restored.to_persistence_payload() == payload
    return restored


def _choose(
    session: LocalGameSession,
    choice: DecisionRequest,
    option_id: str,
    result_id: str,
    next_kind: str,
) -> DecisionRequest:
    return request(
        session.submit_option(
            request_id=choice.request_id,
            option_id=option_id,
            result_id=result_id,
        ),
        next_kind,
    )


def _health(session: LocalGameSession) -> int:
    state = session.lifecycle.state
    assert state is not None
    return sum(
        model.current_wounds
        for model in rules_unit_view_by_id(state=state, unit_instance_id=SUBJECT).own_models
    )


def _positions(session: LocalGameSession) -> tuple[Pose, ...]:
    state = session.lifecycle.state
    assert state is not None
    battlefield = state.battlefield_state
    assert battlefield is not None
    return tuple(model.pose for model in battlefield.unit_placement_by_id(SUBJECT).model_placements)


@pytest.mark.parametrize("case", ["territorial-terror", "outside-shadow", "excluded-monster"])
def test_native_ordered_retreat_resolves_and_replays(
    retreat_definitions: Section02Definitions, case: str
) -> None:
    forced = case != "excluded-monster"
    terror = case == "territorial-terror"
    sheet = SPAWN if forced else DAEMON_PRINCE
    mode = "desperate_escape" if forced else "ordered_retreat"
    d = retreat_definitions
    battle = scene(
        d,
        (selection(d, sheet, "retreat"), selection(d, LORD, "spare")),
        (selection(d, BLOODLETTERS, "letters"),),
        detachment_id_by_faction=DETACHMENTS,
        seed=f"core-09-07-01-{mode}",
    )
    if terror:
        battle.state.battle_round = 2
    subject = battle.units[SUBJECT]
    x = 29 if case == "outside-shadow" else 10
    starts = grid(subject, x, 10)
    ends = tuple(Pose.at(p.position.x, p.position.y - 4) for p in starts)
    locate(battle, SUBJECT, starts)
    locate(battle, FORCER, grid(battle.units[FORCER], x, 12.3 if forced else 12.45))
    locate(battle, SPARE, (Pose.at(38 if case == "outside-shadow" else 30, 30),))
    anchor(battle)

    session = battle.session
    health_before = _health(session)
    pick = request(session.advance_until_decision_or_terminal(), "select_movement_unit")
    action = _choose(session, pick, SUBJECT, "audit-select", "select_movement_action")
    proposal = _choose(session, action, ORDINARY, "audit-fall-back", "submit_movement_proposal")
    context = MovementProposalRequest.from_decision_request_payload(proposal.payload).context
    assert context is not None
    assert context["source_selected_option_id"] == ORDINARY
    assert context["fall_back_mode"] == mode
    if forced:
        assert context["declared_fall_back_mode"] == "ordered_retreat"
        sources = cast(list[dict[str, JsonValue]], context["forced_desperate_escape_sources"])
        (source,) = sources
        assert source["source_kind"] == "catalog_rule_ir"
        assert source["ability_id"] == f"{BLOODLETTERS}:bane-of-cowards"
        assert source["forcing_unit_instance_id"] == FORCER
        assert source["fall_back_unit_instance_id"] == SUBJECT
        assert source["required_fall_back_mode"] == "desperate_escape"
    else:
        assert "forced_desperate_escape_sources" not in context

    restored = _restore(session)
    assert restored.lifecycle.pending_decision_request() == proposal
    for current, restore_outcome in ((session, False), (restored, True)):
        status = propose(current, proposal, subject, ends, result_id="audit-witness")
        hazards = events(current, "desperate_escape_roll_resolved")
        assert [row["model_instance_id"] for row in hazards] == (
            list(subject.own_model_ids()) if forced else []
        )
        tests = events(current, "forced_desperate_escape_battle_shock_resolved")
        assert len(tests) == int(forced)
        if forced:
            outcome = BattleShockResult.from_payload(
                cast(BattleShockResultPayload, tests[0]["battle_shock_result"])
            )
            assert not outcome.passed
            assert outcome.leadership_target == 7
            assert outcome.roll_state.current_total == (7 if terror else 6)
            assert outcome.total == 6
            assert [modifier.operand for modifier in outcome.modified_roll.modifiers] == (
                [-1] if terror else []
            )
        if terror:
            allocation = request(status, "select_mortal_wound_model")
            assert mortal_wound_resolution_progress(allocation).mortal_wounds == 2
            assert events(current, "movement_activation_completed") == []
            assert _health(current) == health_before
            assert _positions(current) == starts
            if restore_outcome:
                current = _restore(current)
                restored = current
                assert current.lifecycle.pending_decision_request() == allocation
            second = _choose(
                current,
                allocation,
                allocation.options[0].option_id,
                "allocate-terror-1",
                "select_mortal_wound_model",
            )
            progress = mortal_wound_resolution_progress(second)
            assert progress.remaining_mortal_wounds == 1
            assert progress.ignored_mortal_wounds == 1  # Native Spawn Feel No Pain.
            assert events(current, "movement_activation_completed") == []
            finished = _choose(
                current,
                second,
                second.options[0].option_id,
                "allocate-terror-2",
                "select_movement_unit",
            )
            (applied,) = events(current, TERROR_APPLIED)
            assert applied["target_unit_instance_id"] == SUBJECT
            assert applied["player_id"] == "opponent"
            damage = MortalWoundApplication.from_payload(
                cast(MortalWoundApplicationPayload, applied["mortal_wound_application"])
            )
            assert damage.mortal_wounds == 2
            assert damage.remaining_mortal_wounds_lost == 0
            assert _health(current) == health_before - (2 - damage.ignored_mortal_wounds)
        else:
            finished = request(status, "select_movement_unit")
            assert events(current, TERROR_APPLIED) == []
            assert _health(current) == health_before
        assert SPARE in {option.option_id for option in finished.options}
        assert SUBJECT not in {option.option_id for option in finished.options}
        (completed,) = events(current, "movement_activation_completed")
        assert completed["unit_instance_id"] == SUBJECT
        assert completed["fall_back_mode"] == mode
        assert _positions(current) == ends

    assert session.to_persistence_payload() == restored.to_persistence_payload()
    _restore(session)
    replay = ReplayRunner.from_payload(session.replay_artifact(artifact_id=case)).run()
    assert replay.reproduced_exactly, replay.to_payload()


def _select_review_retreat(
    session: LocalGameSession, unit_id: str, *, prefix: str = "audit"
) -> DecisionRequest:
    pick = request(session.advance_until_decision_or_terminal(), "select_movement_unit")
    action = _choose(session, pick, unit_id, f"{prefix}-select", "select_movement_action")
    return _choose(session, action, ORDINARY, f"{prefix}-fall-back", "submit_movement_proposal")


def _review_scene(d: Section02Definitions, *, two_retreats: bool) -> Scene:
    outside = (selection(d, SPAWN, "outside"),) if two_retreats else ()
    bodyguards = (selection(d, "000004080", "infractors"),) if two_retreats else ()
    outside_letters = (selection(d, BLOODLETTERS, "outside-letters"),) if two_retreats else ()
    battle = scene(
        d,
        (selection(d, SPAWN, "retreat"), *outside, selection(d, LORD, "spare"), *bodyguards),
        (selection(d, BLOODLETTERS, "letters"), *outside_letters),
        attachments=(AttachmentDeclaration("spare", "infractors"),) if two_retreats else (),
        detachment_id_by_faction=DETACHMENTS,
        seed="core-09-07-01-desperate_escape",
    )
    locate(battle, SUBJECT, grid(battle.units[SUBJECT], 10, 10))
    locate(battle, FORCER, grid(battle.units[FORCER], 10, 12.3))
    locate(battle, SPARE, (Pose.at(31, 35),))
    if two_retreats:
        locate(battle, "own:infractors", grid(battle.units["own:infractors"], 33, 35))
        locate(battle, "own:outside", grid(battle.units["own:outside"], 29, 10))
        locate(battle, "foe:outside-letters", grid(battle.units["foe:outside-letters"], 29, 12.3))
    else:
        battle.state.battle_round = 2
    anchor(battle)
    return battle


def test_second_forced_retreat_uses_only_territory_contributors(
    retreat_definitions: Section02Definitions,
) -> None:
    battle = _review_scene(retreat_definitions, two_retreats=True)
    session = battle.session
    first = _select_review_retreat(session, "own:outside")
    request(
        propose(
            session,
            first,
            battle.units["own:outside"],
            (Pose.at(29, 6), Pose.at(31, 6)),
            result_id="audit-witness",
        ),
        "select_movement_unit",
    )
    assert battle.state.battle_shocked_unit_ids == ["own:outside"]
    assert events(session, TERROR_APPLIED) == []
    second = _select_review_retreat(session, SUBJECT, prefix="second")
    restored = _restore(session)

    for current, restore_pending in ((session, False), (restored, True)):
        status = propose(
            current,
            second,
            battle.units[SUBJECT],
            (Pose.at(10, 6), Pose.at(12, 6)),
            result_id="second-witness",
        )
        allocation = request(status, "select_mortal_wound_model")
        progress = mortal_wound_resolution_progress(allocation)
        rolled_mortals = progress.mortal_wounds
        assert ":daemonic-terror:" in progress.application_id
        _, test = events(current, "forced_desperate_escape_battle_shock_resolved")
        result = BattleShockResult.from_payload(
            cast(BattleShockResultPayload, test["battle_shock_result"])
        )
        assert not result.passed
        assert [modifier.operand for modifier in result.modified_roll.modifiers] == [-1]
        assert _positions(current) == (Pose.at(10, 10), Pose.at(12, 10))
        if restore_pending:
            restored = current = _restore(current)
            assert current.lifecycle.pending_decision_request() == allocation
        for index in range(rolled_mortals):
            status = current.submit_option(
                request_id=allocation.request_id,
                option_id=allocation.options[0].option_id,
                result_id=f"second-allocate-{index}",
            )
            if index + 1 < rolled_mortals:
                allocation = request(status, "select_mortal_wound_model")
        hazard = request(status, "select_mortal_wound_model")
        hazard_progress = mortal_wound_resolution_progress(hazard)
        assert hazard_progress.application_id == f"desperate-escape:{second.request_id}:hazards"
        assert hazard_progress.mortal_wounds == 1
        _choose(
            current,
            hazard,
            hazard.options[0].option_id,
            "second-hazard",
            "select_movement_unit",
        )
        (applied,) = events(current, TERROR_APPLIED)
        assert applied["target_unit_instance_id"] == SUBJECT
        damage = MortalWoundApplication.from_payload(
            cast(MortalWoundApplicationPayload, applied["mortal_wound_application"])
        )
        assert damage.mortal_wounds == rolled_mortals
        completed = events(current, "movement_activation_completed")
        assert [row["unit_instance_id"] for row in completed] == ["own:outside", SUBJECT]
        assert _positions(current) == (Pose.at(10, 6), Pose.at(12, 6))

    assert session.to_persistence_payload() == restored.to_persistence_payload()
    _restore(session)
    replay = ReplayRunner.from_payload(
        session.replay_artifact(artifact_id="second-forced-escape")
    ).run()
    assert replay.reproduced_exactly, replay.to_payload()


def test_forced_escape_restore_rejects_invented_pretest_shock(
    retreat_definitions: Section02Definitions, monkeypatch: pytest.MonkeyPatch
) -> None:
    from warhammer40k_core.engine import battle_shock_modifier_continuation as continuation

    battle = _review_scene(retreat_definitions, two_retreats=False)
    session = battle.session
    proposal = _select_review_retreat(session, SUBJECT)
    resolve = continuation.resolve_battle_shock_after_modifier_choices

    def forge(**kwargs: Any) -> BattleShockResolutionResult:
        assert kwargs["phase_start_battle_shocked_unit_ids"] == ()
        kwargs["phase_start_battle_shocked_unit_ids"] = (FORCER,)
        return resolve(**kwargs)

    with monkeypatch.context() as patch:
        # Generate the linked records and roll through the real resolver with
        # an invented pre-test inventory. The actual Battle-shock history is intact.
        patch.setattr(continuation, "resolve_battle_shock_after_modifier_choices", forge)
        status = propose(
            session,
            proposal,
            battle.units[SUBJECT],
            (Pose.at(10, 6), Pose.at(12, 6)),
            result_id="audit-witness",
        )
    request(status, "select_movement_unit")
    (event,) = events(session, "forced_desperate_escape_battle_shock_resolved")
    result = BattleShockResult.from_payload(
        cast(BattleShockResultPayload, event["battle_shock_result"])
    )
    assert result.modified_roll.modifiers == ()
    assert result.total == 6
    assert events(session, TERROR_APPLIED) == []
    with pytest.raises(
        GameLifecycleError, match="Forced Desperate Escape pre-test Battle-shock state drifted"
    ):
        GameLifecycle.from_payload(json.loads(json.dumps(session.lifecycle.to_payload())))


@pytest.fixture(scope="module")
def walker_retreat_definitions(selected_army_source_index: Path | None) -> Section02Definitions:
    heights = tuple(
        ModelHeightOverride(
            datasheet_id,
            name,
            height,
            GeometrySourceUnits.INCHES,
            f"test:walker-terror:{name}",
            "Level-board Battle-shock fixture.",
        )
        for datasheet_id, name, height in (
            (BOYZ, "BOY", 1.5),
            (BOYZ, "BOSS NOB", 1.6),
            (DEFF_DREAD, "Deff Dread", 2.5),
        )
    )
    source_composition = wahapedia_bridge._composition_entries  # pyright: ignore[reportPrivateUsage]
    source_rows = wahapedia_bridge._rows_matching  # pyright: ignore[reportPrivateUsage]

    def boyz_composition(
        *,
        context: wahapedia_bridge._BridgeContext,  # pyright: ignore[reportPrivateUsage]
        datasheet_id: str,
    ) -> tuple[wahapedia_bridge._CompositionEntry, ...]:  # pyright: ignore[reportPrivateUsage]
        entries = source_composition(context=context, datasheet_id=datasheet_id)
        if datasheet_id != BOYZ:
            return entries
        return tuple(
            replace(entry, model_name="Boy") if entry.model_name == "Boyz" else entry
            for entry in entries
        )

    def standard_loadout_rows(
        rows: dict[str, tuple[NormalizedSourceRow, ...]],
        table: str,
        column: str,
        value: str,
    ) -> tuple[NormalizedSourceRow, ...]:
        if table == "Datasheets_options" and value in (BOYZ, DEFF_DREAD):
            return ()
        return source_rows(rows, table, column, value)

    def selected_catalog(package: CanonicalCatalogPackage) -> CanonicalCatalogPackage:
        return package

    # Normalize the Boyz spelling for default gear and bypass the unrelated
    # complete-catalog Deadly Demise overlay for this three-datasheet selection.
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(
            "tools.generate_ability_support_matrix.BLOODLETTERS_HEIGHT_OVERRIDES",
            (*BLOODLETTERS_HEIGHT_OVERRIDES, *heights),
        )
        patch.setattr(wahapedia_bridge, "_composition_entries", boyz_composition)
        patch.setattr(wahapedia_bridge, "_rows_matching", standard_loadout_rows)
        patch.setattr(
            "tools.generate_ability_support_matrix.with_current_deadly_demise",
            selected_catalog,
        )
        package = _ability_support_catalog_package(
            datasheet_ids=(BOYZ, DEFF_DREAD, BLOODLETTERS),
            source_index_dir=selected_army_source_index,
        )
    catalog = package.army_catalog
    faction_ids = {"ORK": "orks", "CD": "chaos-daemons"}
    factions = tuple(
        replace(faction, faction_id=faction_ids[faction.faction_id]) for faction in catalog.factions
    )
    source_detachments = {row.detachment_id: row for row in identities.detachment_rows()}
    detachments: list[DetachmentDefinition] = []
    for faction in factions:
        row = source_detachments[WALKER_DETACHMENTS[faction.faction_id]]
        detachments.append(
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
                force_disposition_ids=tuple(
                    sorted(
                        {
                            row.force_disposition_id,
                            "take-and-hold",
                            "purge-the-foe",
                        }
                    )
                ),
                source_ids=row.source_ids,
                stratagem_ids=(HUGE_SHOW_OFFS,) if faction.faction_id == "orks" else (),
            )
        )
    huge_show_offs = StratagemDefinition(
        stratagem_id=HUGE_SHOW_OFFS,
        name="Huge Show-Offs",
        source_id=f"phase17e:stratagem:orks:more-dakka:{HUGE_SHOW_OFFS}",
        command_point_cost=1,
        timing_tags=("command",),
    )
    return Section02Definitions(
        replace(
            package,
            army_catalog=replace(
                catalog,
                factions=factions,
                detachments=tuple(detachments),
                stratagems=(*catalog.stratagems, huge_show_offs),
            ),
        ),
        0.0,
    )


@pytest.mark.parametrize(
    ("seed", "total", "passed", "terror_wounds"),
    [
        pytest.param(2, 1, False, 1, id="fail-and-wounds"),
        pytest.param(9, 10, True, 0, id="pass-and-restore"),
        pytest.param(0, 4, False, 2, id="terror-casualty-before-hazards"),
    ],
)
def test_native_ordered_retreat_with_active_walker_objective_control(
    walker_retreat_definitions: Section02Definitions,
    seed: int,
    total: int,
    passed: bool,
    terror_wounds: int,
) -> None:
    definitions = walker_retreat_definitions
    battle = scene(
        definitions,
        (selection(definitions, BOYZ, "retreat"), selection(definitions, DEFF_DREAD, "dread")),
        (selection(definitions, BLOODLETTERS, "letters"),),
        phase=BattlePhase.COMMAND,
        seed="walker-terror",
        rng_seed_label=f"walker-terror:{seed}",
        detachment_id_by_faction=WALKER_DETACHMENTS,
    )
    mission = battle.state.mission_setup
    assert mission is not None
    (home,) = (zone for zone in mission.deployment_zones if zone.player_id == "owner")
    (marker,) = (
        item
        for item in mission.objective_markers
        if home.contains_point(item.x_inches, item.y_inches)
    )
    x, y = marker.x_inches, marker.y_inches
    letters = tuple(
        Pose.at(x - 2.64 + 1.32 * (index % 5), y - 0.70 + 1.4 * (index // 5)) for index in range(10)
    )
    # Move the rear rank first so it clears the front rank's path.
    boyz = tuple(
        Pose.at(x - 2.96 + 1.48 * (index % 5), y - 4.72 + 2.4 * (index // 5)) for index in range(10)
    )
    locate(battle, SUBJECT, boyz)
    locate(battle, FORCER, letters)
    locate(battle, WALKER, (Pose.at(x, y + 3.6),))
    anchor(battle)

    session = battle.session
    state = battle.state
    bundle = session.lifecycle._require_runtime_content_bundle()  # pyright: ignore[reportPrivateUsage]
    grant = state.gain_command_points(
        player_id="owner",
        amount=1,
        source_id="walker-fixture-reserve",
        source_kind=CommandPointSourceKind.COMMAND_PHASE_START,
    )
    assert grant.status is CommandPointGainStatus.APPLIED
    stratagem = request(
        request_stratagem_use_from_index(
            state=state,
            decisions=session.lifecycle.decision_controller,
            index=bundle.stratagem_indexes_by_player_id["owner"],
            context=StratagemEligibilityContext.from_state(
                state=state,
                player_id="owner",
                trigger_kind=TimingTriggerKind.START_PHASE,
            ),
        ),
        "use_stratagem",
    )
    assert session.advance_until_decision_or_terminal().decision_request == stratagem
    waaagh = _choose(
        session,
        stratagem,
        f"use-stratagem:{HUGE_SHOW_OFFS}:target:{WALKER}",
        "walker-command-0",
        "select_faction_rule_command_phase_start_option",
    )
    _choose(session, waaagh, "orks:waaagh:decline", "walker-command-1", "select_movement_unit")
    (used,) = state.stratagem_use_records
    assert used.stratagem_id == HUGE_SHOW_OFFS
    assert used.targeted_unit_instance_ids == (WALKER,)

    objective = resolve_objective_control(
        ObjectiveControlContext.from_game_state(
            state,
            timing=ObjectiveControlTiming.PHASE_END,
            phase=BattlePhase.MOVEMENT,
            ruleset_descriptor=state.runtime_ruleset_descriptor(),
        )
    ).result_by_objective_id(marker.objective_marker_id)
    assert objective.controlled_by_player_id == "opponent"
    assert {score.player_id: score.score for score in objective.scores} == {
        "owner": 14,
        "opponent": 20,
    }
    (walker,) = (model for model in objective.contributors if model.unit_instance_id == WALKER)
    assert walker.effective_objective_control == 4

    retreat = _select_review_retreat(session, SUBJECT)
    subject = battle.units[SUBJECT]
    ends = tuple(Pose.at(pose.position.x, pose.position.y - 3.0) for pose in boyz)
    expected_ends = dict(zip(subject.own_model_ids(), ends, strict=True))
    boss_nob = next(model_id for model_id in expected_ends if ":boss-nob:" in model_id)
    status = propose(session, retreat, subject, ends, result_id="walker-witness")
    assert len(events(session, "desperate_escape_roll_resolved")) == 10
    (test,) = events(session, "forced_desperate_escape_battle_shock_resolved")
    outcome = BattleShockResult.from_payload(
        cast(BattleShockResultPayload, test["battle_shock_result"])
    )
    assert outcome.passed is passed
    assert outcome.leadership_target == 7
    assert outcome.roll_state.current_total == total + 1
    assert outcome.total == total
    assert [modifier.operand for modifier in outcome.modified_roll.modifiers] == [-1]

    pending = request(status)
    session = _restore(session)
    assert session.lifecycle.pending_decision_request() == pending
    if not passed:
        allocation = request(status, "select_mortal_wound_model")
        progress = mortal_wound_resolution_progress(allocation)
        assert progress.application_id == f"{outcome.result_id}:daemonic-terror:{SUBJECT}"
        assert progress.mortal_wounds == terror_wounds
        assert allocation.options[0].option_id == boss_nob
        assert events(session, "movement_activation_completed") == []
        status = session.submit_option(
            request_id=allocation.request_id,
            option_id=allocation.options[0].option_id,
            result_id="walker-wounds-0",
        )
        (applied,) = events(session, TERROR_APPLIED)
        assert applied["target_unit_instance_id"] == SUBJECT
        assert applied["player_id"] == "opponent"
        damage = MortalWoundApplication.from_payload(
            cast(MortalWoundApplicationPayload, applied["mortal_wound_application"])
        )
        assert damage.mortal_wounds == terror_wounds
        assert damage.remaining_mortal_wounds_lost == 0
        assert damage.ignored_mortal_wounds == 0
        assert {wound.model_instance_id for wound in damage.applications} == {boss_nob}
        assert sum(wound.wounds_lost for wound in damage.applications) == terror_wounds
        lethal = damage.applications[-1].destroyed
        assert lethal is (terror_wounds == 2)
        if lethal:
            hazard = request(status, "select_mortal_wound_model")
            hazard_progress = mortal_wound_resolution_progress(hazard)
            assert hazard_progress.application_id.endswith(":hazards")
            assert hazard_progress.mortal_wounds == 2
            session = _restore(session)
            assert session.lifecycle.pending_decision_request() == hazard
            checkpoint = session.lifecycle.state
            assert checkpoint is not None
            assert checkpoint.battlefield_state is not None
            assert boss_nob in checkpoint.battlefield_state.removed_model_ids
            assert checkpoint.battlefield_state.model_placement_or_none(boss_nob) is None
    else:
        assert events(session, TERROR_APPLIED) == []

    # Finish any separately recorded escape hazard allocations.
    allocation_index = int(not passed)
    while (pending := request(status)).decision_type == "select_mortal_wound_model":
        assert mortal_wound_resolution_progress(pending).application_id.endswith(":hazards")
        status = session.submit_option(
            request_id=pending.request_id,
            option_id=pending.options[0].option_id,
            result_id=f"walker-wounds-{allocation_index}",
        )
        allocation_index += 1
    request(status, "select_movement_unit")
    (completed,) = events(session, "movement_activation_completed")
    assert completed["unit_instance_id"] == SUBJECT
    assert completed["fall_back_mode"] == "desperate_escape"
    if terror_wounds == 2:
        assert completed["prior_battle_shock_casualty_ids"] == [boss_nob]
        hazard_ids = completed["destroyed_model_ids"]
        assert isinstance(hazard_ids, list)
        assert all(isinstance(model_id, str) for model_id in hazard_ids)
        hazard_ids = cast(list[str], hazard_ids)
        assert len(hazard_ids) == 2
        assert boss_nob not in hazard_ids
        event_log = session.lifecycle.decision_controller.event_log.records
        event_types = [event.event_type for event in event_log]
        ordering = (
            "forced_desperate_escape_battle_shock_resolved",
            TERROR_APPLIED,
            "desperate_escape_hazard_mortals_started",
            "desperate_escape_hazard_mortals_resolved",
            "desperate_escape_hazard_movement_continued",
            "movement_activation_completed",
        )
        assert [event_types.index(kind) for kind in ordering] == sorted(
            event_types.index(kind) for kind in ordering
        )
        deaths = events(session, "model_logical_death_recorded")
        assert [row["model_instance_id"] for row in deaths] == [boss_nob, *hazard_ids]
        final = session.lifecycle.state
        assert final is not None
        assert final.battlefield_state is not None
        battlefield = final.battlefield_state
        assert set(battlefield.removed_model_ids) == {boss_nob, *hazard_ids}
        placed = battlefield.unit_placement_by_id(SUBJECT)
        assert {model.model_instance_id: model.pose for model in placed.model_placements} == {
            model_id: pose
            for model_id, pose in expected_ends.items()
            if model_id not in battlefield.removed_model_ids
        }
        assert final.current_battle_phase is BattlePhase.MOVEMENT
        assert WALKER in {option.option_id for option in pending.options}
    assert _restore(session).lifecycle.pending_decision_request() == pending
    replay = ReplayRunner.from_payload(session.replay_artifact(artifact_id=f"walker:{seed}")).run()
    assert replay.reproduced_exactly, replay.to_payload()
