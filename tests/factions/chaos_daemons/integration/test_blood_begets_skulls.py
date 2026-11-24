"""Blood Begets Skulls through the live Movement and Charge decisions."""

from dataclasses import replace
from pathlib import Path

import pytest

from tests.daemons_native_source_helpers import BELAKOR, native_definitions
from tests.support.faction_batch01 import (
    CRUSHERS,
    LORD,
    Scene,
    anchor,
    events,
    locate,
    scene,
    selection,
    submit_translation,
)
from tests.support.faction_batch01 import request as require_request
from tests.support.section02_fixtures import Section02Definitions
from tests.support.section04_fixtures import pending
from tests.support.section11_fixtures import begin
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.detachment import DetachmentDefinition
from warhammer40k_core.engine.charge_effects import (
    CHARGE_AFTER_ADVANCE_EFFECT_KIND,
    charge_after_advance_allowed_by_effects,
)
from warhammer40k_core.engine.command_points import CommandPointSourceKind
from warhammer40k_core.engine.decision_request import DecisionError, DecisionRequest
from warhammer40k_core.engine.effects import EffectExpiration
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatus
from warhammer40k_core.engine.replay import ReplayRunner
from warhammer40k_core.engine.stratagems import (
    DECLINE_STRATAGEM_WINDOW_OPTION_ID,
    stratagem_window_context_from_request,
)
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_blood_legion_ir_support_2026_27 as blood_legion_ir,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_detachments_2026_27 as identities,
)

STRATAGEM_ID = blood_legion_ir.BLOOD_BEGETS_SKULLS_STRATAGEM_ID
SOURCE_ID = (
    "gw-11e-phase17e-exact-faction-subrules-2026-27:"
    f"{blood_legion_ir.BLOOD_BEGETS_SKULLS_SOURCE_ROW_ID}"
)
DETACHMENTS = {
    "chaos-daemons": "blood-legion",
    "emperors-children": "court-of-the-phoenician",
}
FIRST = "own:first"
SECOND = "own:second"
WRONG_KEYWORD = "own:undivided"
ENEMY = "foe:target"


@pytest.fixture(scope="module")
def skulls_definitions(selected_army_source_index: Path | None) -> Section02Definitions:
    native = native_definitions(selected_army_source_index)
    catalog = native.package.army_catalog
    source_factions = {"CD": "chaos-daemons", "EC": "emperors-children"}
    factions = tuple(
        replace(faction, faction_id=source_factions[faction.faction_id])
        for faction in catalog.factions
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
            force_disposition_ids=tuple(
                sorted({row.force_disposition_id, "take-and-hold", "purge-the-foe"})
            ),
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


def _scene(
    definitions: Section02Definitions,
    *,
    cp: int,
    phase: BattlePhase = BattlePhase.MOVEMENT,
    turn: str = "owner",
) -> Scene:
    battle = scene(
        definitions,
        (
            selection(definitions, CRUSHERS, "first"),
            selection(definitions, CRUSHERS, "second"),
            selection(definitions, BELAKOR, "undivided"),
        ),
        (selection(definitions, LORD, "target"),),
        phase=phase,
        active=turn,
        detachment_id_by_faction=DETACHMENTS,
        seed="blood-begets-skulls",
    )
    locate(battle, FIRST, tuple(Pose.at(11.0, y) for y in (8.0, 11.0, 14.0)))
    locate(battle, SECOND, tuple(Pose.at(11.0, y) for y in (24.0, 27.0, 30.0)))
    locate(battle, WRONG_KEYWORD, (Pose.at(45.0, 35.0),))
    locate(battle, ENEMY, (Pose.at(21.0, 19.0),))
    if cp:
        battle.state.gain_command_points(
            player_id="owner",
            amount=cp,
            source_id="blood-begets-skulls:fixture-cp",
            source_kind=CommandPointSourceKind.OTHER,
            cap_exempt=True,
        )
    anchor(battle)
    return battle


def _submit(session: LocalGameSession, option: str) -> LifecycleStatus:
    req = pending(session)
    return session.submit_option(
        request_id=req.request_id,
        result_id=f"{req.request_id}:skulls",
        option_id=option,
    )


def _reach_charge(battle: Scene, *, advance: tuple[str, ...]) -> DecisionRequest:
    begin(battle.session)
    for unit in (FIRST, SECOND, WRONG_KEYWORD):
        assert pending(battle.session).decision_type == "select_movement_unit"
        require_request(_submit(battle.session, unit), "select_movement_action")
        if unit in advance:
            proposal = require_request(
                _submit(battle.session, "advance"), "submit_movement_proposal"
            )
            require_request(submit_translation(battle, proposal, unit, 0.5))
            advanced = battle.state.advanced_unit_state_for_unit(
                player_id="owner", battle_round=1, unit_instance_id=unit
            )
            assert advanced is not None
            assert not advanced.can_declare_charge
        else:
            require_request(_submit(battle.session, "remain_stationary"))
    req = pending(battle.session)
    if req.decision_type == "start_mission_action":
        req = require_request(_submit(battle.session, "continue_to_shooting"))
    if req.decision_type == "select_shooting_unit":
        req = require_request(_submit(battle.session, "complete_shooting_phase"))
    return req


def _targets(request: DecisionRequest) -> dict[str, str]:
    targets: dict[str, str] = {}
    for option in request.options:
        if not option.option_id.startswith(f"use-stratagem:{STRATAGEM_ID}:"):
            continue
        assert isinstance(option.payload, dict)
        binding = option.payload["target_binding"]
        assert isinstance(binding, dict)
        unit_id = binding["target_unit_instance_id"]
        assert isinstance(unit_id, str)
        targets[unit_id] = option.option_id
    return targets


def _assert_grant(battle: Scene, target: str, *, remaining_cp: int) -> None:
    assert battle.state.command_point_total("owner") == remaining_cp
    (use,) = tuple(
        use for use in battle.state.stratagem_use_records if use.stratagem_id == STRATAGEM_ID
    )
    assert use.targeted_unit_instance_ids == (target,)
    assert use.source_id == SOURCE_ID
    assert use.command_point_cost == 1
    (grant_event,) = events(battle.session, "generic_stratagem_charge_after_advance_registered")
    (effect,) = tuple(
        effect
        for effect in battle.state.persisting_effects
        if effect.source_rule_id == SOURCE_ID
        and isinstance(effect.effect_payload, dict)
        and effect.effect_payload.get("effect_kind") == CHARGE_AFTER_ADVANCE_EFFECT_KIND
    )
    assert effect.target_unit_instance_ids == (target,)
    assert effect.expiration == EffectExpiration.end_phase(
        battle_round=1, phase=BattlePhase.CHARGE, player_id="owner"
    )
    assert grant_event["persisting_effect"] == effect.to_payload()
    assert all(
        charge_after_advance_allowed_by_effects(state=battle.state, unit_instance_id=unit_id)
        == (unit_id == target)
        for unit_id in (FIRST, SECOND, WRONG_KEYWORD, ENEMY)
    )


@pytest.mark.integration
def test_blood_begets_skulls_offers_when_advance_prevents_all_charges(
    skulls_definitions: Section02Definitions,
) -> None:
    battle = _scene(skulls_definitions, cp=2)
    offer = _reach_charge(battle, advance=(FIRST, SECOND))
    assert offer.decision_type == "use_stratagem"
    assert offer.actor_id == "owner"
    assert set(_targets(offer)) == {FIRST, SECOND}
    assert battle.state.charge_phase_state is not None
    assert battle.state.charge_phase_state.selected_unit_ids == ()
    assert not events(battle.session, "charging_unit_selection_requested")

    checkpoint = battle.session.to_persistence_payload()
    restored = LocalGameSession.from_persistence_payload(checkpoint)
    assert restored.to_persistence_payload() == checkpoint
    alternative = require_request(_submit(restored, DECLINE_STRATAGEM_WINDOW_OPTION_ID))
    assert not _targets(alternative)
    assert not events(restored, "charging_unit_selection_requested")
    assert not events(restored, "stratagem_used")

    with pytest.raises(DecisionError, match="option"):
        _submit(battle.session, _targets(offer)[FIRST].replace(FIRST, WRONG_KEYWORD))
    assert pending(battle.session) == offer
    assert battle.state.command_point_total("owner") == 2

    charge = require_request(
        _submit(battle.session, _targets(offer)[FIRST]), "select_charging_unit"
    )
    assert {option.option_id for option in charge.options} == {FIRST, "complete_charge_phase"}
    assert battle.state.charge_phase_state.selected_unit_ids == ()
    _assert_grant(battle, FIRST, remaining_cp=1)
    active = battle.session.to_persistence_payload()
    assert LocalGameSession.from_persistence_payload(active).to_persistence_payload() == active
    require_request(_submit(battle.session, "complete_charge_phase"))
    assert battle.state.current_battle_phase is not BattlePhase.CHARGE
    assert not charge_after_advance_allowed_by_effects(state=battle.state, unit_instance_id=FIRST)
    replay = ReplayRunner.from_payload(battle.session.replay_artifact(artifact_id="skulls")).run()
    assert replay.reproduced_exactly, replay


@pytest.mark.integration
def test_blood_begets_skulls_decline_then_offer_after_earlier_charge(
    skulls_definitions: Section02Definitions,
) -> None:
    battle = _scene(skulls_definitions, cp=2)
    first_offer = _reach_charge(battle, advance=(SECOND,))
    assert set(_targets(first_offer)) == {FIRST, SECOND}
    charge = require_request(
        _submit(battle.session, DECLINE_STRATAGEM_WINDOW_OPTION_ID), "select_charging_unit"
    )
    assert {option.option_id for option in charge.options} == {FIRST, "complete_charge_phase"}
    later = require_request(_submit(battle.session, FIRST))
    if later.decision_type == "use_stratagem" and not _targets(later):
        later = require_request(_submit(battle.session, DECLINE_STRATAGEM_WINDOW_OPTION_ID))
    if later.decision_type == "select_charge_targets":
        later = require_request(_submit(battle.session, "decline_charge_targets"))
    assert later.decision_type == "use_stratagem"
    assert set(_targets(later)) == {SECOND}
    assert (
        stratagem_window_context_from_request(first_offer).timing_window_id
        != stratagem_window_context_from_request(later).timing_window_id
    )
    assert battle.state.charge_phase_state is not None
    assert battle.state.charge_phase_state.selected_unit_ids == (FIRST,)
    resumed = require_request(
        _submit(battle.session, _targets(later)[SECOND]), "select_charging_unit"
    )
    assert {option.option_id for option in resumed.options} == {SECOND, "complete_charge_phase"}
    _assert_grant(battle, SECOND, remaining_cp=1)
    assert battle.state.charge_phase_state.selected_unit_ids == (FIRST,)
    replay = ReplayRunner.from_payload(
        battle.session.replay_artifact(artifact_id="skulls-later")
    ).run()
    assert replay.reproduced_exactly, replay


@pytest.mark.integration
def test_blood_begets_skulls_unavailable_without_cp_or_outside_own_charge(
    skulls_definitions: Section02Definitions,
) -> None:
    battle = _scene(skulls_definitions, cp=0)
    charge = _reach_charge(battle, advance=(SECOND,))
    assert charge.decision_type == "select_charging_unit"
    assert {option.option_id for option in charge.options} == {FIRST, "complete_charge_phase"}
    assert not battle.state.stratagem_use_records

    wrong_phase = _scene(skulls_definitions, cp=2, phase=BattlePhase.SHOOTING)
    shooting = begin(wrong_phase.session)
    assert wrong_phase.state.current_battle_phase is BattlePhase.SHOOTING
    assert not _targets(shooting)

    wrong_turn = _scene(skulls_definitions, cp=2, phase=BattlePhase.CHARGE, turn="opponent")
    opponent_charge = begin(wrong_turn.session)
    assert opponent_charge.decision_type == "select_charging_unit"
    assert opponent_charge.actor_id == "opponent"
    assert not _targets(opponent_charge)
    assert not wrong_turn.state.stratagem_use_records
