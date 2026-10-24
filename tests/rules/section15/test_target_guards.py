"""Section-owned target/window boundaries, with declared keyword supplements."""

from dataclasses import replace

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section15_fixtures import binding, checkpoint, context, record
from tests.unit_keyword_helpers import with_unit_keywords
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.stratagems_selection import _stratagem_unavailable_reason
from warhammer40k_core.engine.timing_windows import TimingTriggerKind


@pytest.mark.parametrize(("distance", "legal"), [(1, False), (8, True)])
def test_overwatch_excludes_engaged_shooter_with_native_unengaged_control(
    section15_definitions: Section02Definitions, distance: float, legal: bool
) -> None:
    _session, state, unit, _ = checkpoint(
        section15_definitions, phase=BattlePhase.MOVEMENT, active="opponent", distance=distance
    )
    before = state.to_payload()
    reason = _stratagem_unavailable_reason(
        state=state,
        record=record("fire-overwatch"),
        context=context(state, TimingTriggerKind.END_PHASE),
        target_binding=binding(unit),
        effect_selection=None,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        army_catalog=section15_definitions.package.army_catalog,
    )
    assert (reason is None) is legal
    assert state.to_payload() == before


@pytest.mark.parametrize(
    ("kind", "phase", "active", "trigger", "keyword", "legal"),
    [
        (
            "fire-overwatch",
            BattlePhase.MOVEMENT,
            "opponent",
            TimingTriggerKind.END_PHASE,
            None,
            True,
        ),
        ("fire-overwatch", BattlePhase.MOVEMENT, "owner", TimingTriggerKind.END_PHASE, None, False),
        (
            "fire-overwatch",
            BattlePhase.SHOOTING,
            "opponent",
            TimingTriggerKind.END_PHASE,
            None,
            False,
        ),
        (
            "fire-overwatch",
            BattlePhase.MOVEMENT,
            "opponent",
            TimingTriggerKind.START_PHASE,
            None,
            False,
        ),
        (
            "fire-overwatch",
            BattlePhase.MOVEMENT,
            "opponent",
            TimingTriggerKind.END_PHASE,
            "TITANIC",
            False,
        ),
        (
            "smokescreen",
            BattlePhase.SHOOTING,
            "opponent",
            TimingTriggerKind.START_PHASE,
            "SMOKE",
            True,
        ),
        (
            "smokescreen",
            BattlePhase.SHOOTING,
            "owner",
            TimingTriggerKind.START_PHASE,
            "SMOKE",
            False,
        ),
        (
            "smokescreen",
            BattlePhase.SHOOTING,
            "opponent",
            TimingTriggerKind.START_PHASE,
            None,
            False,
        ),
        (
            "heroic-intervention",
            BattlePhase.CHARGE,
            "owner",
            TimingTriggerKind.END_PHASE,
            None,
            False,
        ),
        (
            "epic-challenge",
            BattlePhase.SHOOTING,
            "owner",
            TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_SELECTED_TO_FIGHT,
            None,
            False,
        ),
        ("explosives", BattlePhase.SHOOTING, "owner", TimingTriggerKind.DURING_PHASE, None, True),
        (
            "explosives",
            BattlePhase.SHOOTING,
            "opponent",
            TimingTriggerKind.DURING_PHASE,
            None,
            False,
        ),
        ("explosives", BattlePhase.MOVEMENT, "owner", TimingTriggerKind.DURING_PHASE, None, False),
    ],
)
def test_catalog_window_turn_and_target_keyword_restrictions(
    section15_definitions: Section02Definitions,
    kind: str,
    phase: BattlePhase,
    active: str,
    trigger: TimingTriggerKind,
    keyword: str | None,
    legal: bool,
) -> None:
    session, state, unit, enemy = checkpoint(
        section15_definitions, phase=phase, active=active, materialize=False
    )
    own = state.army_definition_for_player("owner")
    assert own is not None
    native = own.unit_by_id(unit)
    if keyword:
        changed = with_unit_keywords(native, keywords=(*native.keywords, keyword))
        state.army_definitions[:] = [
            replace(a, units=(changed,)) if a.player_id == "owner" else a
            for a in state.army_definitions
        ]
        assert changed.own_model_ids() == native.own_model_ids()
        assert [m.geometry for m in changed.own_models] == [m.geometry for m in native.own_models]
    session.lifecycle._require_runtime_content_bundle()  # pyright: ignore[reportPrivateUsage]
    ctx = context(state, trigger, {"selected_unit_instance_id": unit})
    before = state.to_payload()
    effect: JsonValue = {"mode": "into_the_fray"} if kind == "heroic-intervention" else None
    if kind == "explosives":
        effect = {
            "effect_selection_kind": "source_model_and_enemy_unit",
            "source_model_instance_id": native.own_model_ids()[0],
            "enemy_target_unit_instance_id": enemy,
        }
    reason = _stratagem_unavailable_reason(
        state=state,
        record=record(kind),
        context=ctx,
        target_binding=binding(unit),
        effect_selection=effect,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        army_catalog=section15_definitions.package.army_catalog,
    )
    assert (reason is None) is legal
    assert state.to_payload() == before
