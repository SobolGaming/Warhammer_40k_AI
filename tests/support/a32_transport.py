"""A32 original public setup family; constructed Core equipment is explicit.

The terrain-cleared mission and constructed destruction profile match the audit.
No official roster/provider or selected native fixture admission is claimed.
"""

from dataclasses import replace
from functools import lru_cache

from tests.d10_profile_helpers import profile_catalog
from tests.deployment_submission_helpers import deployment_placement_payload_for_request
from tests.order60_emergency_disembark_helpers import emergency_disembark_unit_placement
from tests.order135_transport_helpers import CARRIER as CARRIER
from tests.order135_transport_helpers import PASSENGER as PASSENGER
from tests.order135_transport_helpers import transport_config
from tests.phase13b_shooting_declaration_helpers import _proposal_from_request
from tests.support.section04_fixtures import weapon_rows

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.weapon_profiles import (
    AttackProfile,
    DamageProfile,
    RangeProfile,
    WeaponKeyword,
)
from warhammer40k_core.engine.battlefield_state import BattlefieldPlacementKind
from warhammer40k_core.engine.damage_allocation import unit_by_id
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.game_state import GameConfig
from warhammer40k_core.engine.movement_proposals import PlacementProposalPayload, ProposalKind
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.stratagems import stratagem_decline_payload
from warhammer40k_core.engine.transports import DisembarkModeKind, TransportMovementStatus
from warhammer40k_core.geometry.pose import Pose


@lru_cache(maxsize=1)
def destruction_config() -> GameConfig:
    config = transport_config()
    pcat = profile_catalog()
    catalog = replace(
        config.army_catalog,
        datasheets=tuple(
            next(x for x in pcat.datasheets if x.datasheet_id == d.datasheet_id)
            if d.datasheet_id == "core-character-leader"
            else d
            for d in config.army_catalog.datasheets
        ),
        wargear=tuple(
            replace(
                w,
                weapon_profiles=tuple(
                    replace(
                        p,
                        range_profile=RangeProfile.distance(60),
                        attack_profile=AttackProfile.fixed(2),
                        strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 30),
                        armor_penetration=CharacteristicValue.from_raw(
                            Characteristic.ARMOR_PENETRATION, -6
                        ),
                        damage_profile=DamageProfile.fixed(30),
                        keywords=(*p.keywords, WeaponKeyword.TORRENT),
                        source_ids=(*p.source_ids, "audit:predeclared-d04-destruction-profile"),
                    )
                    for p in w.weapon_profiles
                ),
            )
            if w.wargear_id == "core-bolt-rifle"
            else w
            for w in config.army_catalog.wargear
        ),
    )
    return replace(
        config,
        game_id="audit-d04-native-emergency-1",
        army_catalog=catalog,
        turn_order=("player-b", "player-a"),
    )


def submit_next(session: LocalGameSession, request: DecisionRequest) -> None:
    state = session.lifecycle.state
    assert state is not None
    ids = [x.option_id for x in request.options]
    payload: JsonValue = None
    option: str | None = None
    if request.decision_type == "submit_deployment_placement":
        payload = deployment_placement_payload_for_request(
            session.lifecycle,
            request=request,
            pose_factory=lambda i, owner, m: Pose.at(
                10 if owner == "player-a" else 50, 10 + 1.5 * i
            ),
        )
    elif request.decision_type == "submit_stratagem_target_proposal":
        payload = stratagem_decline_payload()
    elif (
        request.decision_type == "select_shooting_unit"
        and "army-beta:enemy" in ids
        and not state.disembarked_unit_states
    ):
        option = "army-beta:enemy"
    elif request.decision_type == "select_shooting_type":
        option = "normal"
    elif request.decision_type == "submit_shooting_declaration":
        rows = weapon_rows(request)
        weapon = next(x for x in rows if x["wargear_id"] == "core-bolt-rifle")
        payload = validate_json_value(
            _proposal_from_request(
                request=request,
                target_unit_id=CARRIER,
                weapon_profile_id=str(weapon["weapon_profile_id"]),
            ).to_payload()
        )
    else:
        option = (
            "fixed:assassination:bring_it_down"
            if request.decision_type == "select_secondary_missions"
            else next(
                (
                    x
                    for x in ids
                    if x.startswith(("complete_", "end_", "decline", "skip"))
                    or x == "remain_stationary"
                ),
                ids[0] if ids else None,
            )
        )
    result_id = f"a32:{request.request_id}"
    if payload is not None:
        result = session.submit_parameterized_payload(
            request_id=request.request_id, result_id=result_id, payload=payload
        )
    else:
        assert option is not None
        result = session.submit_option(
            request_id=request.request_id, result_id=result_id, option_id=option
        )
    assert result.status_kind is not LifecycleStatusKind.INVALID, result.to_payload()


def pending_emergency(*, destroyed_cargo: bool = False) -> LocalGameSession:
    config = destruction_config()
    if destroyed_cargo:
        catalog = replace(
            config.army_catalog,
            datasheets=tuple(
                replace(
                    d,
                    model_profiles=tuple(
                        replace(
                            m,
                            characteristics=tuple(
                                CharacteristicValue.from_raw(Characteristic.WOUNDS, 1)
                                if v.characteristic is Characteristic.WOUNDS
                                else v
                                for v in m.characteristics
                            ),
                        )
                        for m in d.model_profiles
                    ),
                )
                if d.datasheet_id == "core-character-leader"
                else d
                for d in config.army_catalog.datasheets
            ),
        )
        config = replace(config, game_id="audit-a32-all-dead-1", army_catalog=catalog)
    session = LocalGameSession()
    session.start(config)
    for _ in range(60):
        status = session.advance_until_decision_or_terminal()
        request = status.decision_request
        assert request is not None, status.to_payload()
        if request.decision_type == "submit_placement_proposal":
            assert not destroyed_cargo
            return session
        if destroyed_cargo and any(
            e.event_type == "attack_sequence_completed"
            for e in session.lifecycle.decision_controller.event_log.records
        ):
            return session
        submit_next(session, request)
    raise AssertionError("Original destruction did not reach its expected boundary")


def emergency_payload(
    session: LocalGameSession, request: DecisionRequest, *, far: bool = False
) -> JsonValue:
    state = session.lifecycle.state
    assert state is not None
    placement = emergency_disembark_unit_placement(
        unit_by_id(state=state, unit_instance_id=PASSENGER),
        army_id="army-alpha",
        player_id="player-a",
        center_x=30 if far else 10,
        center_y=10,
    )
    return validate_json_value(
        PlacementProposalPayload(
            proposal_request_id=request.request_id,
            proposal_kind=ProposalKind.DISEMBARK,
            unit_instance_id=PASSENGER,
            placement_kind=BattlefieldPlacementKind.DISEMBARK,
            attempted_placement=placement,
            transport_unit_instance_id=CARRIER,
            disembark_mode=DisembarkModeKind.EMERGENCY_DISEMBARK,
            transport_movement_status=TransportMovementStatus.NOT_MOVED,
        ).to_payload()
    )
