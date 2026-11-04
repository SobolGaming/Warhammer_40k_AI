"""Native selected-pool components; no army muster or facade replay certification."""

from __future__ import annotations

import json
from dataclasses import replace
from functools import cache
from itertools import combinations
from pathlib import Path

from tools.generate_ability_support_matrix import (
    _ability_support_catalog_package,  # pyright: ignore[reportPrivateUsage]
)

from tests.support.section02_consumers import attack_pool
from tests.support.section02_fixtures import Section02Definitions
from tests.support.section03_fixtures import geometry, placement
from tests.support.section04_fixtures import combat_state
from warhammer40k_core.engine.attack_sequence import (
    AttackSequence,
    apply_allocation_order_decision,
    apply_attack_weapon_group_decision,
    apply_damage_allocation_model_decision,
    apply_feel_no_pain_decision,
    apply_resolve_target_unit_decision,
    resolve_attack_sequence_until_blocked,
)
from warhammer40k_core.engine.attack_sequence_psychic_modifiers import (
    selection_from_payload,
    validate_psychic_attack_modifier_ignore_decision,
)
from warhammer40k_core.engine.damage_allocation import DamageKind, apply_damage_to_model, unit_by_id
from warhammer40k_core.engine.damaged_effects import (
    catalog_damaged_effect_hit_roll_modifier_bindings,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import canonical_json
from warhammer40k_core.engine.game_state import (
    GameState,
)
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.wargear_selections import ModelProfileSelection
from warhammer40k_core.engine.weapon_instances import equipped_weapon_profile_instances_for_model
from warhammer40k_core.geometry.pose import Pose

BELAKOR = "000001148"
SELECTED = (BELAKOR, "000001115", "000001114")


@cache
def native_definitions(index: Path | None) -> Section02Definitions:
    # The three EC definitions are existing canonical checkpoint dependencies:
    # default state construction, enemy body and the distant spare unit.
    return Section02Definitions(
        _ability_support_catalog_package(
            datasheet_ids=(*SELECTED, "000004080", "000004078", "000004090"),
            source_index_dir=index,
        ),
        0.0,
    )


def damaged_state(
    d: Section02Definitions, wounds: int, phase: BattlePhase, *, target: UnitInstance | None = None
) -> GameState:
    unit = d.unit(BELAKOR)
    state = combat_state(
        d, unit, phase=phase, distance=3.2 if phase is BattlePhase.FIGHT else 8, target=target
    )
    assert unit.own_models[0].wounds_remaining == 20
    if wounds < 20:
        result = apply_damage_to_model(
            state=state,
            target_unit_instance_id=unit.unit_instance_id,
            model_instance_id=unit.own_model_ids()[0],
            damage=20 - wounds,
            damage_kind=DamageKind.MORTAL,
        )
        assert result.final_wounds_remaining == wounds
    return state


def attack_component(
    d: Section02Definitions, phase: BattlePhase, *, seed: int = 0
) -> tuple[GameState, AttackSequence]:
    # Native ten-model EC target keeps the full 7/9-attack component meaningful;
    # the separate native Bloodletters Sv7 allocation defect is not repaired here.
    target = d.unit(
        "000004080",
        identity="target",
        army_id="enemy",
        composition=tuple(
            ModelProfileSelection(p.model_profile_id, p.max_models)
            for p in d.package.army_catalog.datasheet_by_id("000004080").composition
        ),
    )
    assert len(target.own_models) == 10
    state = damaged_state(d, 7, phase, target=target)
    # Two compact columns use the unchanged native circular base diameter.
    diameters = {
        p.base_size.diameter_mm
        for p in d.package.army_catalog.datasheet_by_id("000004080").model_profiles
    }
    (diameter,) = diameters
    assert diameter is not None
    spacing = diameter / 25.4 + 0.05
    x = 13.2 if phase is BattlePhase.FIGHT else 18.0
    poses = tuple(Pose.at(x + spacing * (i % 2), 10 + spacing * (i // 2)) for i in range(10))
    models = (
        *geometry(target, poses, enemy=True),
        *geometry(
            unit_by_id(state=state, unit_instance_id="section02:subject"), (Pose.at(10, 10),)
        ),
    )
    assert all(not a.base_overlaps(b) for a, b in combinations(models, 2))
    assert state.battlefield_state is not None
    state.replace_battlefield_state(
        replace(
            state.battlefield_state,
            placed_armies=tuple(
                replace(a, unit_placements=(placement(target, poses, enemy=True),))
                if a.player_id == "opponent"
                else a
                for a in state.battlefield_state.placed_armies
            ),
        )
    )
    # The kernel appends target starting strength after the owner; use the
    # authoritative serialized order before declaring this component origin.
    state.starting_strength_records.sort(key=lambda record: record.unit_instance_id)
    state.game_id = f"daemons-native:damaged:{phase.value}:seed-{seed}"
    own = unit_by_id(state=state, unit_instance_id="section02:subject")
    profile_id = BELAKOR + (
        ":the-blade-of-shadows:strike"
        if phase is BattlePhase.FIGHT
        else ":betraying-shades:witchfire"
    )
    physical = next(
        weapon
        for weapon in equipped_weapon_profile_instances_for_model(
            model=own.own_models[0], army_catalog=d.package.army_catalog
        )
        if weapon.weapon_profile.profile_id == profile_id
    )
    pool = replace(
        attack_pool(own, target, physical.weapon_profile, physical.wargear_id),
        weapon_instance_id=physical.weapon_instance_id,
    )
    assert pool.attacks == (7 if phase is BattlePhase.FIGHT else 9)
    # Already selected native pool: declaration, army admission and complete
    # ability/provider lifecycles are outside this component's proven boundary.
    return state, AttackSequence(
        "native-damaged", "owner", own.unit_instance_id, (pool,), source_phase=phase
    )


def resolve_native_attack(
    d: Section02Definitions,
    phase: BattlePhase,
    *,
    ignore: bool,
    seed: int,
    restore: bool,
) -> tuple[GameState, DecisionController, int]:
    state, initial_sequence = attack_component(d, phase, seed=seed)
    sequence: AttackSequence | None = initial_sequence
    decisions = DecisionController()
    allocated: tuple[str, ...] = ()
    choices = 0
    registry = RuntimeModifierRegistry.from_bindings(
        hit_roll_modifier_bindings=catalog_damaged_effect_hit_roll_modifier_bindings(
            armies=tuple(state.army_definitions)
        )
    )

    def roundtrip() -> None:
        nonlocal state, sequence, decisions, allocated
        rng_before = DiceRollManager(state.game_id, event_log=decisions.event_log).rng.to_payload()
        before = (
            state.to_payload(),
            decisions.to_payload(),
            None if sequence is None else sequence.to_payload(),
            list(allocated),
        )
        allocated = tuple(json.loads(json.dumps(before[3])))
        assert allocated == tuple(before[3])
        state = GameState.from_payload(json.loads(json.dumps(before[0])))
        decisions = DecisionController.from_payload(json.loads(json.dumps(before[1])))
        sequence = (
            None
            if before[2] is None
            else AttackSequence.from_payload(json.loads(json.dumps(before[2])))
        )
        assert canonical_json(list(before)) == canonical_json(
            [
                state.to_payload(),
                decisions.to_payload(),
                None if sequence is None else sequence.to_payload(),
                list(allocated),
            ]
        )
        # The production manager reconstructs seed/history/draw position from
        # the complete event journal; it has no separate persistence payload.
        assert (
            DiceRollManager(state.game_id, event_log=decisions.event_log).rng.to_payload()
            == rng_before
        )

    if restore:
        roundtrip()
    for _ in range(120):
        if sequence is None:
            if restore:
                roundtrip()
            return state, decisions, choices
        if not decisions.queue.pending_requests:
            sequence, allocated, status = resolve_attack_sequence_until_blocked(
                state=state,
                decisions=decisions,
                ruleset_descriptor=state.runtime_ruleset_descriptor(),
                attack_sequence=sequence,
                already_allocated_model_ids=allocated,
                runtime_modifier_registry=registry,
                dice_manager=DiceRollManager(state.game_id, event_log=decisions.event_log),
            )
            if sequence is None:
                assert status is None
                continue
        if restore:
            roundtrip()
        assert sequence is not None
        request = decisions.queue.peek_next()
        if request.decision_type == "select_psychic_attack_modifier_ignores":
            selection = selection_from_payload(request.payload)
            assert selection.hit_roll_modifier == -1
            assert len(selection.modifiers) == 1
            term = selection.modifiers[0]
            assert term.modifier.source_id is not None
            assert "damaged" in term.modifier.source_id
            option = next(
                o
                for o in request.options
                if selection_from_payload(o.payload).ignored_modifier_ids
                == ((term.modifier_id,) if ignore else ())
                and len(selection_from_payload(o.payload).decided_modifier_ids) == 1
            )
            choices += 1
        else:
            assert request.decision_type in {
                "select_damage_allocation_model",
                "select_allocation_order",
                "select_mortal_wound_model",
                "select_resolve_target_unit",
                "select_attack_weapon_group",
            }, request.decision_type
            option = request.options[0]
        result = DecisionResult.for_request(
            result_id=request.request_id + ":native-choice",
            request=request,
            selected_option_id=option.option_id,
        )
        decisions.submit_result(result)
        if request.decision_type == "select_psychic_attack_modifier_ignores":
            validate_psychic_attack_modifier_ignore_decision(
                state=state,
                decisions=decisions,
                attack_sequence=sequence,
                result=result,
                runtime_modifier_registry=registry,
            )
        elif request.decision_type in {"select_resolve_target_unit", "select_attack_weapon_group"}:
            apply_selection = (
                apply_resolve_target_unit_decision
                if request.decision_type == "select_resolve_target_unit"
                else apply_attack_weapon_group_decision
            )
            sequence = apply_selection(decisions=decisions, attack_sequence=sequence, result=result)
        else:
            apply_allocation = (
                apply_feel_no_pain_decision
                if request.decision_type == "select_mortal_wound_model"
                else apply_allocation_order_decision
                if request.decision_type == "select_allocation_order"
                else apply_damage_allocation_model_decision
            )
            sequence, allocated, _ = apply_allocation(
                state=state,
                decisions=decisions,
                ruleset_descriptor=state.runtime_ruleset_descriptor(),
                attack_sequence=sequence,
                result=result,
                already_allocated_model_ids=allocated,
                runtime_modifier_registry=registry,
            )
        if restore:
            roundtrip()
    raise AssertionError("Native selected-pool attack did not complete")
