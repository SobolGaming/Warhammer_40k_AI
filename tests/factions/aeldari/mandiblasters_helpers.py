"""Native component checkpoints; accepted facade charge and ordinary fight resolution."""

from __future__ import annotations

import math

from tests.factions.aeldari.current_source_helpers import charge
from tests.psychic_modifier_helpers import submit_fixture_request
from tests.support.faction_batch01 import Scene, anchor, events, locate, scene, selection
from tests.support.section02_fixtures import Section02Definitions
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.weapon_profiles import WeaponProfile
from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.list_validation import UnitMusterSelection
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.runtime_modifiers import HitRollMinimumUnmodifiedSuccessContext
from warhammer40k_core.geometry.pose import Pose

SCORPIONS = "000000595"
WALKERS = "000000612"


def scorpion_scene(
    d: Section02Definitions,
    *,
    charged: bool = True,
    attached: bool = False,
    scorpion_equipment: tuple[str, ...] = (),
    leader_equipment: tuple[str, ...] = (),
    perform_charge: bool = True,
    one_bodyguard: bool = False,
) -> Scene:
    from warhammer40k_core.engine.list_validation import AttachmentDeclaration

    own: tuple[UnitMusterSelection, ...] = (
        selection(d, SCORPIONS, "scorpions", equipment=scorpion_equipment),
    )
    if attached:
        own += (selection(d, "000000577", "autarch", equipment=leader_equipment),)
    s = scene(
        d,
        own,
        (selection(d, WALKERS, "walkers"),),
        phase=BattlePhase.CHARGE if charged else BattlePhase.FIGHT,
        seed="independent-mandiblasters-charge",
        attachments=(AttachmentDeclaration("autarch", "scorpions"),) if attached else (),
    )
    radius = (60 + 28.5) / 50.8
    endpoints = tuple(
        Pose.at(
            14 - radius * math.cos(math.radians(angle)),
            12.4 + radius * math.sin(math.radians(angle)),
        )
        for angle in (-80, -40, 0, 40, 80)
    )
    locate(
        s,
        "own:scorpions",
        tuple(
            Pose.at(5.5, 12.4)
            if attached and i == 4
            else Pose.at(p.position.x - (5 if charged else 0), p.position.y)
            for i, p in enumerate(endpoints)
        ),
    )
    locate(s, "foe:walkers", (Pose.at(14, 12.4),))
    if attached:
        from tests.order130_helpers import session_from_casualty_checkpoint
        from tests.phase11c_command_phase_helpers import destroy_models_with_recorded_mortal_wounds

        # A legal native five-model bodyguard was mustered. The checkpoint has
        # one ordinary prior casualty, leaving room for the leader's charge.
        radius = (60 + 32) / 50.8 + 1e-10
        point = Pose.at(
            14 - radius * math.cos(math.radians(80)), 12.4 + radius * math.sin(math.radians(80))
        )
        locate(
            s, "own:autarch", (Pose.at(point.position.x - (5 if charged else 0), point.position.y),)
        )
        anchor(s)
        ids = s.units["own:scorpions"].own_model_ids()
        casualties = tuple(mid for mid in ids if mid != ids[2]) if one_bodyguard else ids[-1:]
        destroy_models_with_recorded_mortal_wounds(
            state=s.state,
            decisions=s.session.lifecycle.decision_controller,
            unit_instance_id="attached-unit:own:scorpions",
            model_instance_ids=casualties,
            application_id="native-retention:prior-casualties",
            destroying_player_id="opponent",
        )
        s.session = session_from_casualty_checkpoint(s.session.lifecycle)
    else:
        anchor(s)
    if charged and perform_charge:
        for _ in range(10):
            status = s.session.advance_until_decision_or_terminal()
            pending = status.decision_request
            assert pending is not None
            if pending.decision_type == "select_charging_unit":
                break
            submit_fixture_request(s.session, pending)
        else:
            raise AssertionError("Native charging selection not reached")
        charge(
            s, "attached-unit:own:scorpions" if attached else "own:scorpions", "foe:walkers", 5.0
        )
    return s


def finish_first_attack(s: Scene) -> None:
    for _ in range(150):
        if events(s.session, "attack_sequence_completed"):
            return
        status = s.session.advance_until_decision_or_terminal()
        request = status.decision_request
        assert request is not None, status
        submit_fixture_request(s.session, request)
    raise AssertionError("Native attack did not complete")


def hit_context(
    s: Scene, profile: WeaponProfile, model_id: str
) -> HitRollMinimumUnmodifiedSuccessContext:
    return HitRollMinimumUnmodifiedSuccessContext(
        s.state,
        BattlePhase.FIGHT,
        s.state.unit_instance_id_for_model(model_id),
        model_id,
        "foe:walkers",
        profile,
        (),
        2,
    )


def indexes(s: Scene) -> tuple[tuple[str, AbilityCatalogIndex], ...]:
    bundle = s.session.lifecycle._require_runtime_content_bundle()  # pyright: ignore[reportPrivateUsage]
    return bundle.runtime_modifier_registry.modifier_permission_indexes


def hit_payloads(s: Scene) -> list[dict[str, JsonValue]]:
    result: list[dict[str, JsonValue]] = []
    for event in events(s.session, "attack_sequence_step"):
        if event["step"] == "hit":
            payload = event["payload"]
            assert isinstance(payload, dict)
            result.append(payload)
    return result


def restored_scene(s: Scene) -> Scene:
    session = LocalGameSession.from_persistence_payload(s.session.to_persistence_payload())
    state = session.lifecycle.state
    assert state is not None
    return Scene(
        session, state, {u.unit_instance_id: u for a in state.army_definitions for u in a.units}
    )
