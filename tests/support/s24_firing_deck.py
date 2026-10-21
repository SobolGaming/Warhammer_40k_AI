"""S24 uses admitted native definitions, with declared Core Firing Deck/cargo inputs.

The ordinary Trukk/Boyz loader rejects missing representative heights. Rather
than invent provider admission, use the admitted Wave Serpent and Infractors
with an explicit Firing Deck 2 grant and constructed capacity/cargo checkpoint.
No official carrier ability, faction roster or preceding setup is certified.
"""

from dataclasses import replace
from typing import cast

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section03_fixtures import native_state
from tests.support.section04_fixtures import body, shooting_payload
from tests.support.section07_fixtures import boundary_session
from tests.support.section09_fixtures import add_unit, attach_mission, unplace
from tests.support.section24_fixtures import BODY, LORD, SERPENT, with_core

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.weapon_profiles import WeaponKeyword
from warhammer40k_core.engine.command_points import CommandPointSourceKind
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.engine.stratagems import (
    StratagemTargetBinding,
    StratagemTargetKind,
    StratagemTargetProposal,
    StratagemTargetProposalPayload,
    stratagem_decline_payload,
)
from warhammer40k_core.engine.transports import TransportCapacityProfile, TransportCargoState
from warhammer40k_core.geometry.pose import Pose

CARRIER = "section02:carrier"
CARGO = "section02:cargo"
ENEMY = "enemy:target"


def scene(d: Section02Definitions, *, own_phase: bool = False) -> LocalGameSession:
    carrier = with_core(d.unit(SERPENT, identity="carrier"), "firing-deck", "2")
    passenger = d.unit(BODY, identity="cargo")
    target = d.unit(LORD, army_id="enemy", identity="target")
    state = native_state(
        d, carrier, (Pose.at(10, 10),), enemy=target, enemy_poses=(Pose.at(18, 10),)
    )
    add_unit(
        state,
        passenger,
        tuple(Pose.at(9 + i % 5, 18 + i // 5) for i in range(len(passenger.own_models))),
    )
    state.replace_battlefield_state(unplace(state, passenger))
    state.record_transport_cargo_state(
        TransportCargoState(
            "owner",
            CARRIER,
            TransportCapacityProfile(
                SERPENT, 12, ("INFANTRY",), source_id="constructed:s24:capacity"
            ),
            (CARGO,),
        )
    )
    state.battle_phase_index = state.battle_phase_sequence.index(
        BattlePhase.SHOOTING if own_phase else BattlePhase.MOVEMENT
    )
    state.active_player_id = "owner" if own_phase else "opponent"
    state.turn_order = ("owner", "opponent") if own_phase else ("opponent", "owner")
    state.gain_command_points(
        player_id="owner",
        amount=2,
        source_id="constructed:s24:resource-checkpoint",
        source_kind=CommandPointSourceKind.OTHER,
        cap_exempt=True,
    )
    attach_mission(state)
    assert state.mission_setup is not None
    state.mission_setup = replace(
        state.mission_setup,
        deployment_map_id="constructed:s24:zones",
        terrain_layout_id="constructed:s24:clear",
        battlefield_regions=(),
    )
    state.ruleset_descriptor_hash = state.runtime_ruleset_descriptor().descriptor_hash
    state.starting_strength_records.sort(key=lambda r: r.unit_instance_id)
    return boundary_session(d, state)


def request_body(request: DecisionRequest) -> dict[str, JsonValue]:
    return cast(dict[str, JsonValue], body(request)["proposal_request"])


def reach_declaration(session: LocalGameSession, *, own_phase: bool = False) -> DecisionRequest:
    """Ordinary phase handlers discover a real opponent end-Movement Overwatch."""
    used = False
    for i in range(40):
        status = session.advance_until_decision_or_terminal()
        request = status.decision_request
        assert request is not None, status
        if request.decision_type == "submit_shooting_declaration":
            return request
        payload: JsonValue = None
        if request.decision_type == "submit_stratagem_target_proposal":
            proposal = StratagemTargetProposal.from_payload(
                cast(StratagemTargetProposalPayload, request_body(request))
            )
            if (
                proposal.stratagem_id == "fire-overwatch"
                and request.actor_id == "owner"
                and not used
            ):
                bound = proposal.with_binding(
                    StratagemTargetBinding(StratagemTargetKind.FRIENDLY_UNIT, "owner", CARRIER)
                )
                payload = validate_json_value({"proposal": bound.to_payload()})
                used = True
            else:
                payload = stratagem_decline_payload()
        if payload is not None:
            result = session.submit_parameterized_payload(
                request_id=request.request_id, result_id=f"s24:setup:{i}", payload=payload
            )
        else:
            ids = [o.option_id for o in request.options]
            if own_phase and request.decision_type == "select_shooting_unit":
                option = CARRIER
            elif request.decision_type == "select_shooting_type":
                option = "normal"
            else:
                option = next(
                    (
                        s
                        for s in ids
                        if s.startswith(("complete_", "end_", "decline", "skip"))
                        or s in {"remain_stationary", "continue_to_shooting"}
                    ),
                    ids[0],
                )
            result = session.submit_option(
                request_id=request.request_id, result_id=f"s24:setup:{i}", option_id=option
            )
        assert result.status_kind is not LifecycleStatusKind.INVALID, result
    raise AssertionError("S24 declaration not reached through ordinary phase handlers")


def declaration_payload(
    request: DecisionRequest, rows: list[dict[str, JsonValue]], *, borrowed: bool
) -> dict[str, JsonValue]:
    payload = cast(dict[str, JsonValue], shooting_payload(request, rows, [ENEMY] * len(rows)))
    context = request_body(request)
    declarations = cast(list[dict[str, JsonValue]], payload["declarations"])
    for row, declaration in zip(rows, declarations, strict=True):
        declaration["shooting_type"] = context["selected_shooting_type"] or "snap"
        if borrowed:
            declaration["firing_deck_source_unit_instance_id"] = row[
                "firing_deck_source_unit_instance_id"
            ]
            declaration["firing_deck_source_model_instance_id"] = row[
                "firing_deck_source_model_instance_id"
            ]
    if borrowed:
        payload["firing_deck_selection"] = {
            "player_id": request.actor_id,
            "battle_round": context["battle_round"],
            "transport_unit_instance_id": CARRIER,
            "firing_deck_value": 2,
            "already_shot_unit_instance_ids": context["firing_deck_already_shot_unit_instance_ids"]
            or [],
            "weapon_selections": [
                {
                    "embarked_unit_instance_id": row["firing_deck_source_unit_instance_id"],
                    "model_instance_id": row["firing_deck_source_model_instance_id"],
                    "weapon_instance_id": row["weapon_instance_id"],
                    "wargear_id": row["wargear_id"],
                    "weapon_profile": row["weapon_profile"],
                }
                for row in rows
            ],
        }
    return payload


def borrowed_rows(session: LocalGameSession) -> list[dict[str, JsonValue]]:
    """Physical catalog weapons for direct hostile submissions, never advertised authority."""
    from warhammer40k_core.engine.phases.shooting_firing_deck import (
        _available_weapon_to_payload,
        _available_weapons_for_model,
    )

    state = session.lifecycle.state
    assert state is not None
    army = state.army_definition_for_player("owner")
    assert army is not None
    carrier = army.unit_by_id(CARRIER)
    cargo = army.unit_by_id(CARGO)
    result: list[dict[str, JsonValue]] = []
    for model in cargo.own_models:
        weapons = _available_weapons_for_model(
            model=model, army_catalog=session.lifecycle.config.army_catalog
        )
        weapon = next(
            w for w in weapons if WeaponKeyword.ONE_SHOT not in w["weapon_profile"].keywords
        )
        result.append(
            cast(
                dict[str, JsonValue],
                dict(
                    _available_weapon_to_payload(
                        {
                            **weapon,
                            "model_instance_id": carrier.own_model_ids()[0],
                            "firing_deck_source_unit_instance_id": CARGO,
                            "firing_deck_source_model_instance_id": model.model_instance_id,
                        }
                    )
                ),
            )
        )
    return result
