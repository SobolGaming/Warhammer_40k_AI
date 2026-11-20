"""09.07 and both 09.07.01 nodes: modes, hazard consequences and FAQ13."""

from dataclasses import replace
from typing import cast

import pytest

from tests.support.private_randomness import fixture_private_rng_seed
from tests.support.section02_fixtures import Section02Definitions
from tests.support.section03_fixtures import grid, native_state, paths, scenario
from tests.support.section03_session import movement_session
from tests.support.section09_fixtures import (
    add_unit,
    choose,
    events,
    finish_hazard_choices,
    movement_case,
    propose,
    select,
)
from warhammer40k_core.core.datasheet import (
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
    CatalogJsonObject,
    DatasheetAbilityDescriptor,
)
from warhammer40k_core.core.modifiers import RollModifier
from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.ability_catalog import catalog_ability_records_from_catalog
from warhammer40k_core.engine.catalog_desperate_escape import (
    battle_shocked_roll_modifiers_for_record,
)
from warhammer40k_core.engine.dice import DICE_REROLL_DECISION_TYPE, DiceRollManager
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.movement_proposals import (
    MovementProposalPayload,
    MovementProposalRequest,
)
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.phases.movement import (
    DesperateEscapeRoll,
    DesperateEscapeRollPayload,
    FallBackModeKind,
    resolve_fall_back_move,
)
from warhammer40k_core.engine.phases.movement_state import MovementPhaseState
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.geometry import milli_inch_symbolic
from warhammer40k_core.geometry.movement_envelope import MovementDistanceUnresolvedError
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.objective_terminology import ObjectiveRuleScope
from warhammer40k_core.rules.rule_compiler import compile_rule_source_text
from warhammer40k_core.rules.source_data import RuleSourceText
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    datasheet_keyword_lexicon_2026_06_14,
)


@pytest.mark.parametrize("shocked", [False, True])
@pytest.mark.parametrize(
    "mode", [FallBackModeKind.ORDERED_RETREAT, FallBackModeKind.DESPERATE_ESCAPE]
)
def test_selected_desperate_mode_requests_exactly_one_hazard_per_model(
    section09_definitions: Section02Definitions,
    shocked: bool,
    mode: FallBackModeKind,
) -> None:
    unit = section09_definitions.unit("000004090")
    state = native_state(section09_definitions, unit)
    board = scenario(state)
    starts = grid(unit)
    result = resolve_fall_back_move(
        scenario=board,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        unit_placement=board.battlefield_state.unit_placement_by_id(unit.unit_instance_id),
        fall_back_mode=mode,
        path_witness=paths(
            unit, starts, tuple(Pose.at(p.position.x, p.position.y - 4) for p in starts)
        ),
        battle_shocked_unit_ids=(unit.unit_instance_id,) if shocked else (),
    )
    assert result.is_valid
    expected = len(unit.own_models) if shocked or mode is FallBackModeKind.DESPERATE_ESCAPE else 0
    assert len(result.desperate_escape_requirements) == expected
    assert len({r.model_instance_id for r in result.desperate_escape_requirements}) == expected
    for requirement in result.desperate_escape_requirements:
        assert requirement.roll_spec().expression.quantity == 1
        assert requirement.roll_spec().expression.sides == 6


@pytest.mark.parametrize("face", range(1, 7))
@pytest.mark.parametrize("penalty", [0, -1])
def test_desperate_escape_hazard_faces_use_the_modified_value(
    section09_definitions: Section02Definitions,
    face: int,
    penalty: int,
) -> None:
    unit = section09_definitions.unit("000004090")
    state = native_state(section09_definitions, unit)
    board = scenario(state)
    result = resolve_fall_back_move(
        scenario=board,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        unit_placement=board.battlefield_state.unit_placement_by_id(unit.unit_instance_id),
        fall_back_mode=FallBackModeKind.DESPERATE_ESCAPE,
        path_witness=paths(unit, grid(unit), (Pose.at(10, 6), Pose.at(12, 6))),
    )
    requirement = result.desperate_escape_requirements[0]
    # Constructed already-authorized modifier contract. Native Bane source is tested below.
    modifiers = (
        (
            RollModifier(
                modifier_id="constructed:penalty", source_id="constructed:source", operand=penalty
            ),
        )
        if penalty
        else ()
    )
    roll = DesperateEscapeRoll.from_roll_state(
        requirement=requirement,
        roll_state=DiceRollManager(state.private_rng_seed).roll_fixed(
            requirement.roll_spec(), (face,)
        ),
        roll_modifiers=modifiers,
    )
    assert roll.value == max(1, face + penalty)
    assert roll.is_failed is (face + penalty <= 2)
    assert DesperateEscapeRoll.from_payload(roll.to_payload()) == roll


@pytest.mark.parametrize("shocked", [False, True])
def test_native_bane_of_cowards_penalty_applies_only_when_shocked(
    section09_definitions: Section02Definitions,
    shocked: bool,
) -> None:
    catalog = section09_definitions.package.army_catalog
    native = section09_definitions.unit("000001114")
    ability = next(a for a in native.datasheet_abilities if a.name == "Bane of Cowards")
    record = next(
        r
        for r in catalog_ability_records_from_catalog(catalog)
        if r.definition.source_id == ability.source_id
    )
    modifiers = battle_shocked_roll_modifiers_for_record(
        record=record,
        target_unit_instance_id="section02:subject",
        battle_shocked_unit_ids=("section02:subject",) if shocked else (),
    )
    assert len(modifiers) == int(shocked)
    if shocked:
        assert modifiers[0].operand == -1
        assert modifiers[0].source_id == ability.source_id


@pytest.mark.parametrize("mode", ["ordered_retreat", "desperate_escape"])
def test_only_desperate_escape_can_cross_enemy_models_but_both_must_end_unengaged(
    section09_definitions: Section02Definitions,
    mode: str,
) -> None:
    unit = section09_definitions.unit("000004090")
    enemy = section09_definitions.unit("000004090", identity="enemy", army_id="enemy")
    starts = (Pose.at(10, 10), Pose.at(12.5, 10))
    state = native_state(
        section09_definitions,
        unit,
        starts,
        enemy=enemy,
        enemy_poses=(Pose.at(10, 13.8), Pose.at(12.5, 13.8)),
    )
    board = scenario(state)
    result = resolve_fall_back_move(
        scenario=board,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        unit_placement=board.battlefield_state.unit_placement_by_id(unit.unit_instance_id),
        fall_back_mode=FallBackModeKind(mode),
        path_witness=paths(unit, starts, (Pose.at(10, 18), Pose.at(12.5, 18))),
    )
    assert result.is_valid is (mode == "desperate_escape")


@pytest.mark.parametrize(
    "mode", [FallBackModeKind.ORDERED_RETREAT, FallBackModeKind.DESPERATE_ESCAPE]
)
def test_fall_back_cannot_finish_still_engaged(
    section09_definitions: Section02Definitions,
    mode: FallBackModeKind,
) -> None:
    unit = section09_definitions.unit("000004090")
    enemy = section09_definitions.unit("000004090", identity="enemy", army_id="enemy")
    state = native_state(
        section09_definitions, unit, enemy=enemy, enemy_poses=(Pose.at(10, 13.8), Pose.at(12, 13.8))
    )
    board = scenario(state)
    result = resolve_fall_back_move(
        scenario=board,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        unit_placement=board.battlefield_state.unit_placement_by_id(unit.unit_instance_id),
        fall_back_mode=mode,
        path_witness=paths(unit, grid(unit), grid(unit)),
    )
    assert not result.is_valid
    assert any(
        v.violation_code == "enemy_engagement_range_end_forbidden"
        for r in result.path_validation_results
        for v in r.violations
    )


@pytest.mark.parametrize("shocked", [False, True])
def test_failed_escape_hazards_inflict_mortals_instead_of_removing_native_multiwound_models(
    section09_definitions: Section02Definitions,
    shocked: bool,
) -> None:
    session, state, unit = movement_case(section09_definitions, engaged=True)
    state.game_id = "section09-hazard-consequence"
    state.private_rng_seed = fixture_private_rng_seed("section09-hazard-consequence:private-0")
    session = movement_session(section09_definitions, state)
    if shocked:
        state.battle_shocked_unit_ids.append(unit.unit_instance_id)
    request = choose(session, select(session, unit), "fall_back:desperate_escape")
    status = propose(session, request, unit, (Pose.at(10, 6), Pose.at(12.5, 6)))
    rolls = events(session, "desperate_escape_roll_resolved")
    assert len(rolls) == 2
    failed = sum(
        int(
            DesperateEscapeRoll.from_payload(
                cast(DesperateEscapeRollPayload, r["desperate_escape_roll"])
            ).is_failed
        )
        for r in rolls
    )
    assert failed > 0, "This retained seed must exercise a failed hazard."
    # Retained baseline measured the legacy whole-model choice. The corrected
    # consumer uses native Section06 allocation choices; expectations stay exact.
    finish_hazard_choices(session, status)
    assert state.battlefield_state is not None
    assert set(unit.own_model_ids()).issubset(state.battlefield_state.placed_model_ids())
    current = rules_unit_view_by_id(state=state, unit_instance_id=unit.unit_instance_id)
    assert (
        sum(m.current_wounds for m in current.alive_models())
        == sum(m.initial_wounds for m in unit.own_models) - failed
    )


@pytest.mark.parametrize("shocked", [False, True])
def test_all_escape_hazards_are_rolled_as_one_simultaneous_batch(
    section09_definitions: Section02Definitions,
    shocked: bool,
) -> None:
    session, state, unit = movement_case(section09_definitions, engaged=True)
    if shocked:
        state.battle_shocked_unit_ids.append(unit.unit_instance_id)
    request = choose(session, select(session, unit), "fall_back:desperate_escape")
    propose(session, request, unit, (Pose.at(10, 6), Pose.at(12.5, 6)))
    # Simultaneous means all dice precede any consequence or player choice; it
    # does not prescribe the number of internal RNG journal records.
    records = session.lifecycle.decision_controller.event_log.records
    indices = [
        i
        for i, e in enumerate(records)
        if e.event_type == "dice_rolled" and "desperate_escape" in str(e.payload)
    ]
    assert indices
    assert not any(
        e.event_type
        in {
            "decision_requested",
            "model_destroyed",
            "mortal_wound_applied",
            "movement_activation_completed",
        }
        for e in records[indices[0] + 1 : indices[-1]]
    )
    assert len(events(session, "desperate_escape_roll_resolved")) == 2


@pytest.mark.parametrize(
    ("mode", "shocked"),
    [
        (FallBackModeKind.ORDERED_RETREAT, False),
        (FallBackModeKind.DESPERATE_ESCAPE, False),
        (FallBackModeKind.DESPERATE_ESCAPE, True),
    ],
)
def test_faq13_native_auto_pass_permission_covers_desperate_mode_hazards(
    section09_definitions: Section02Definitions,
    mode: FallBackModeKind,
    shocked: bool,
) -> None:
    unit = section09_definitions.unit("000000969")
    enemy = section09_definitions.unit("000004090", identity="enemy", army_id="enemy")
    state = native_state(
        section09_definitions,
        unit,
        (Pose.at(20, 10),),
        enemy=enemy,
        enemy_poses=(Pose.at(20, 14), Pose.at(22.5, 14)),
    )
    board = scenario(state)
    index = AbilityCatalogIndex.from_records(
        catalog_ability_records_from_catalog(section09_definitions.package.army_catalog)
    )
    result = resolve_fall_back_move(
        scenario=board,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        unit_placement=board.battlefield_state.unit_placement_by_id(unit.unit_instance_id),
        state=state,
        ability_index=index,
        fall_back_mode=mode,
        battle_shocked_unit_ids=(unit.unit_instance_id,) if shocked else (),
        path_witness=paths(unit, (Pose.at(20, 10),), (Pose.at(20, 22),)),
    )
    assert result.is_valid, result.to_payload()
    # Native Scuttling Walker auto-pass is consumed, not injected into the tested
    # function. FAQ13 identifies these hazards as the auto-passed tests.
    assert result.desperate_escape_requirements == ()


@pytest.mark.parametrize("shocked", [False, True])
def test_voluntary_escape_tests_battle_shock_after_moving_only_if_not_already_shocked(
    section09_definitions: Section02Definitions,
    shocked: bool,
) -> None:
    session, state, unit = movement_case(section09_definitions, engaged=True)
    state.game_id = "section09-hazard-consequence"
    if shocked:
        state.battle_shocked_unit_ids.append(unit.unit_instance_id)
    request = choose(session, select(session, unit), "fall_back:desperate_escape")
    status = propose(session, request, unit, (Pose.at(10, 6), Pose.at(12.5, 6)))
    finish_hazard_choices(session, status)
    assert state.battlefield_state is not None
    surviving = set(unit.own_model_ids()).intersection(state.battlefield_state.placed_model_ids())
    assert surviving, "Retained deterministic scene must leave a unit for its after-move rule."
    assert len(events(session, "desperate_escape_battle_shock_resolved")) == int(not shocked)
    if not shocked:
        types = [e.event_type for e in session.lifecycle.decision_controller.event_log.records]
        assert (
            types.index("fall_back_move_applied")
            < types.index("desperate_escape_battle_shock_resolved")
            < types.index("movement_activation_completed")
        )


@pytest.fixture(scope="module")
def escape_reroll_definitions(section09_definitions: Section02Definitions) -> Section02Definitions:
    # A narrow catalog fixture grants the genuine rule-IR reroll to the native
    # movement scene without depending on an unadmitted fortification footprint.
    source = RuleSourceText.from_raw(
        objective_scope=ObjectiveRuleScope.CORE_RULES,
        source_id="section09:desperate-escape-reroll",
        raw_text=(
            'While a friendly Khorne Legiones Daemonica unit is within 6" of this '
            "FORTIFICATION, each time you take a Battle-shock test for that unit, you can "
            "re-roll that test."
        ),
    )
    rule_ir = compile_rule_source_text(
        source,
        source_keyword_sequence_parts=(
            datasheet_keyword_lexicon_2026_06_14.canonical_datasheet_keyword_sequence_parts()
        ),
    ).rule_ir
    ability = DatasheetAbilityDescriptor(
        ability_id=source.source_id,
        name="Battle-shock Reroll",
        source_id=source.source_id,
        support=CatalogAbilitySupport.GENERIC_RULE_IR,
        source_kind=CatalogAbilitySourceKind.DATASHEET,
        effect_description=source.raw_text,
        rule_ir_payload=cast(CatalogJsonObject, rule_ir.to_payload()),
    )
    package = section09_definitions.package
    catalog = package.army_catalog
    mover = catalog.datasheet_by_id("000004090")
    provider = catalog.datasheet_by_id("000000599")
    mover = replace(
        mover,
        keywords=replace(
            mover.keywords,
            keywords=(*mover.keywords.keywords, "KHORNE"),
            faction_keywords=(*mover.keywords.faction_keywords, "LEGIONES DAEMONICA"),
        ),
    )
    provider = replace(
        provider,
        keywords=replace(
            provider.keywords, keywords=(*provider.keywords.keywords, "FORTIFICATION")
        ),
        abilities=(*provider.abilities, ability),
        source_ids=tuple(sorted({*provider.source_ids, source.source_id})),
    )
    updated = {mover.datasheet_id: mover, provider.datasheet_id: provider}
    catalog = replace(
        catalog,
        datasheets=tuple(updated.get(row.datasheet_id, row) for row in catalog.datasheets),
        source_ids=tuple(sorted({*catalog.source_ids, source.source_id})),
    )
    return Section02Definitions(replace(package, army_catalog=catalog), 0.0)


@pytest.mark.parametrize("option_id", ["decline", "reroll:0,1"])
def test_native_escape_battle_shock_reroll_reuses_certified_path(
    escape_reroll_definitions: Section02Definitions,
    option_id: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    definitions = escape_reroll_definitions
    _, state, unit = movement_case(definitions, engaged=True)
    provider = definitions.unit("000000599", identity="reroll-provider")
    state.game_id = "section09-hazard-consequence"
    state.private_rng_seed = fixture_private_rng_seed("section09-hazard-consequence:private-0")
    add_unit(state, provider, (Pose.at(17, 7),))
    session = movement_session(definitions, state)
    request = choose(session, select(session, unit), "fall_back:desperate_escape")
    proposal = MovementProposalRequest.from_decision_request_payload(request.payload)
    (first_id, second_id) = unit.own_model_ids()
    witness = PathWitness.for_paths(
        (
            (first_id, (Pose.at(10, 10), Pose.at(10, 8), Pose.at(10, 6))),
            (second_id, (Pose.at(12, 10), Pose.at(12.25, 8), Pose.at(12.5, 6))),
        )
    )
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="escape-path",
        payload=validate_json_value(
            MovementProposalPayload(
                proposal_request_id=request.request_id,
                proposal_kind=proposal.proposal_kind,
                unit_instance_id=unit.unit_instance_id,
                movement_phase_action="fall_back",
                movement_mode="fall_back",
                fall_back_mode="desperate_escape",
                witness=witness,
            ).to_payload()
        ),
    )
    status = finish_hazard_choices(session, status)
    reroll_request = status.decision_request
    assert reroll_request is not None, status.to_payload()
    assert reroll_request.decision_type == DICE_REROLL_DECISION_TYPE
    assert option_id in {option.option_id for option in reroll_request.options}
    assert state.movement_phase_state is not None
    saved_state = state.movement_phase_state.to_payload()
    assert MovementPhaseState.from_payload(saved_state).to_payload() == saved_state

    def unresolved(*_args: object, **_kwargs: object) -> int:
        raise milli_inch_symbolic.UnresolvedDistanceMeasurementError("test clock expired")

    with monkeypatch.context() as patch:
        patch.setattr(milli_inch_symbolic, "symbolic_squared_path_inches_to_ticks", unresolved)
        with pytest.raises(MovementDistanceUnresolvedError):
            MovementPhaseState.from_payload(saved_state)
        completed = session.submit_option(
            request_id=reroll_request.request_id,
            option_id=option_id,
            result_id="escape-reroll",
        )
    assert completed.status_kind is not LifecycleStatusKind.INVALID, completed.to_payload()
    records = session.lifecycle.decision_controller.records
    rerolls = [
        record.result
        for record in records
        if record.request.request_id == reroll_request.request_id
    ]
    assert [(result.result_id, result.selected_option_id) for result in rerolls] == [
        ("escape-reroll", option_id)
    ]
    assert len(events(session, "fall_back_move_applied")) == 1
    assert len(events(session, "desperate_escape_battle_shock_resolved")) == 1
    assert len(events(session, "movement_activation_completed")) == 1
