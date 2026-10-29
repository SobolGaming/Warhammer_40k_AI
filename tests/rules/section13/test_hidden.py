"""13.09/09.01/11.01: terrain producer -> Hidden -> actual shooting target query."""

import pytest

from tests.support.section02_fixtures import (
    CHAOS_SPAWN,
    LORD_EXULTANT,
    MAULERFIEND,
    Section02Definitions,
)
from tests.support.section03_fixtures import axis_endpoint_within_range
from tests.support.section13_fixtures import area, candidate, feature, native_models, recent, scene
from warhammer40k_core.engine.shooting_targets import ShootingTargetViolationCode
from warhammer40k_core.engine.terrain_hidden import terrain_hidden_model_ids
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.terrain_classification import TerrainAreaClassification as C


@pytest.mark.parametrize("classification", [C.EXPOSED, C.LIGHT, C.DENSE])
@pytest.mark.parametrize("sheet", [LORD_EXULTANT, CHAOS_SPAWN, MAULERFIEND])
@pytest.mark.parametrize("when", ["first", "none", "current", "previous", "old"])
def test_hidden_requires_eligible_physical_keyword_area_and_no_recent_shooting(
    section13_definitions: Section02Definitions, classification: C, sheet: str, when: str
) -> None:
    d = section13_definitions
    s, _, target = scene(
        d,
        target_sheet=sheet,
        areas=(area(x=24, classification=classification, width=12, depth=16),),
    )
    recent(s, target, when)
    hidden = terrain_hidden_model_ids(
        state=s,
        ruleset_descriptor=s.runtime_ruleset_descriptor(),
        unit_instance_id=target.unit_instance_id,
    )
    expected = (
        target.own_model_ids()
        if classification is not C.EXPOSED
        and sheet != MAULERFIEND
        and when not in {"current", "previous"}
        else ()
    )
    assert set(hidden) == set(expected)


@pytest.mark.parametrize("gone", [False, True])
@pytest.mark.parametrize(("delta", "legal"), [(-0.01, True), (0, True), (0.01, False)])
def test_native_detection_base_distance_inclusive_fifteen_or_twelve_inches(
    section13_definitions: Section02Definitions, gone: bool, delta: float, legal: bool
) -> None:
    d = section13_definitions
    s, attacker, target = scene(d)
    am = native_models(
        attacker, tuple(Pose.at(10, 10 + 1.5 * i) for i in range(len(attacker.own_models)))
    )[0]
    tm = native_models(target, (Pose.at(24, 10),))[0]
    distance = 12 if gone else 15
    x = axis_endpoint_within_range(10, am.base.max_radius(), tm.base.max_radius(), distance) + delta
    features = (feature(C.DENSE, x=x - 1, depth=0.6, height=4),) if gone else ()
    s, attacker, target = scene(d, target_x=x, areas=(area(x=x),), features=features)
    result = candidate(d, s, attacker, target)
    assert result.is_legal is legal, result.to_payload()
    assert result.violation_code is (
        None if legal else ShootingTargetViolationCode.OUTSIDE_DETECTION_RANGE
    )
    if gone and legal:
        assert result.line_of_sight_witness is not None
        assert not result.line_of_sight_witness.unit_fully_visible


@pytest.mark.parametrize("hidden", [False, True])
@pytest.mark.parametrize("classification", [C.LIGHT, C.DENSE])
@pytest.mark.parametrize("intervenes", [False, True])
def test_gone_to_ground_requires_hidden_and_actual_intervening_dense_feature(
    section13_definitions: Section02Definitions, hidden: bool, classification: C, intervenes: bool
) -> None:
    d = section13_definitions
    s, attacker, target = scene(
        d,
        target_x=24,
        areas=(area(x=24, classification=C.LIGHT if hidden else C.EXPOSED),),
        features=(feature(classification, x=23, y=10 if intervenes else 30, depth=0.6, height=4),),
    )
    result = candidate(d, s, attacker, target)
    # Native edge distance ~12.6: within15 and outside12.
    protected = hidden and classification is C.DENSE and intervenes
    assert result.is_legal is not protected, result.to_payload()


@pytest.mark.parametrize("when", ["current", "previous", "old", "first"])
def test_recent_shooting_blocks_gone_to_ground_even_with_retained_hidden_permission(
    section13_definitions: Section02Definitions, when: str
) -> None:
    d = section13_definitions
    s, attacker, target = scene(
        d, target_x=24, areas=(area(x=24),), features=(feature(C.DENSE, x=23, depth=0.6, height=4),)
    )
    recent(s, target, when)
    # Explicit constructed permission: stay Hidden after shooting, not native admission.
    from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
    from warhammer40k_core.engine.phases.shooting_eligibility import _hidden_target_model_ids
    from warhammer40k_core.engine.ranged_rule_effects import unit_hidden_payload

    s.record_persisting_effect(
        PersistingEffect(
            effect_id="constructed:s13:hidden",
            source_rule_id="constructed:s13:retain-hidden",
            owner_player_id="opponent",
            target_unit_instance_ids=(target.unit_instance_id,),
            started_battle_round=1,
            started_phase=s.current_battle_phase,
            expiration=EffectExpiration.end_of_battle(),
            effect_payload=unit_hidden_payload(source_rule_kind="constructed:s13:permission"),
        )
    )
    assert (
        _hidden_target_model_ids(
            state=s,
            ruleset_descriptor=s.runtime_ruleset_descriptor(),
            target_unit_ids=(target.unit_instance_id,),
        )
        == target.own_model_ids()
    )
    result = candidate(d, s, attacker, target)
    assert result.is_legal is (when in {"current", "previous"}), result.to_payload()


def test_independent_case_mutation_does_not_share_health_abilities_or_history(
    section13_definitions: Section02Definitions,
) -> None:
    d = section13_definitions
    first, a, t = scene(d, areas=(area(x=24),))
    second, b, other = scene(d, areas=(area(x=24),))
    assert first is not second
    assert a is not b
    assert t is not other
    assert t.own_models[0] is not other.own_models[0]
    recent(first, t, "current")
    assert (
        terrain_hidden_model_ids(
            state=first,
            ruleset_descriptor=first.runtime_ruleset_descriptor(),
            unit_instance_id=t.unit_instance_id,
        )
        == ()
    )
    assert (
        terrain_hidden_model_ids(
            state=second,
            ruleset_descriptor=second.runtime_ruleset_descriptor(),
            unit_instance_id=other.unit_instance_id,
        )
        == other.own_model_ids()
    )


@pytest.mark.parametrize("keyword", ["INFANTRY", "BEAST", "SWARM", "VEHICLE", "FLY"])
def test_hidden_uses_constructed_physical_keyword_not_the_unit_name(
    section13_definitions: Section02Definitions, keyword: str
) -> None:
    from dataclasses import replace

    from tests.unit_keyword_helpers import with_unit_keywords

    s, _, target = scene(section13_definitions, areas=(area(x=24),))
    changed = with_unit_keywords(target, keywords=(keyword,))
    s.army_definitions[:] = [
        replace(a, units=(changed,)) if a.player_id == "opponent" else a for a in s.army_definitions
    ]
    hidden = terrain_hidden_model_ids(
        state=s,
        ruleset_descriptor=s.runtime_ruleset_descriptor(),
        unit_instance_id=target.unit_instance_id,
    )
    assert hidden == (target.own_model_ids() if keyword in {"INFANTRY", "BEAST", "SWARM"} else ())
