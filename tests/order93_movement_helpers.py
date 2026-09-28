"""Canonical movement/Charge modifier fixtures and finite facade submissions."""

from dataclasses import replace
from typing import cast

from tests.generic_modifier_helpers import generic_effect
from tests.phase15a_charge_test_support import _charge_lifecycle, _compact_test_unit_poses
from tests.psychic_modifier_helpers import pending_request
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.effects import EffectExpiration
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.geometry.pose import Pose

UNIT_ID = "army-alpha:intercessor-1"


def movement_modifier_session(
    phase: BattlePhase, *, extra_charge_modifiers: int = 0, random_movement: bool = False
) -> LocalGameSession:
    from warhammer40k_core.core.army_catalog import ArmyCatalog
    from warhammer40k_core.core.attributes import Characteristic
    from warhammer40k_core.core.dice import DiceExpression
    from warhammer40k_core.core.random_profile_values import RandomProfileValue

    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    if random_movement:
        sheet = catalog.datasheet_by_id("core-intercessor-like-infantry")
        sheet = replace(
            sheet,
            model_profiles=tuple(
                replace(
                    profile,
                    characteristics=tuple(
                        RandomProfileValue(
                            Characteristic.MOVEMENT, DiceExpression(2, 6), profile.source_ids[0]
                        )
                        if value.characteristic is Characteristic.MOVEMENT
                        else value
                        for value in profile.characteristics
                    ),
                )
                for profile in sheet.model_profiles
            ),
        )
        catalog = replace(
            catalog,
            datasheets=tuple(
                sheet if item.datasheet_id == sheet.datasheet_id else item
                for item in catalog.datasheets
            ),
        )
    lifecycle, _units = _charge_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_model_poses=_compact_test_unit_poses(origin=Pose.at(20, 20), model_count=5),
        game_id=f"order93-{phase.value}",
        catalog=catalog,
    )
    state = lifecycle.state
    assert state is not None
    state.battle_phase_index = state.battle_phase_sequence.index(phase)
    specifications: list[tuple[str, str, dict[str, JsonValue]]] = [
        (
            "permission",
            "grant_ability",
            {"ability": "modifier_ignore_permission", "selection": "any_or_all"},
        )
    ]
    if phase is BattlePhase.CHARGE:
        specifications.extend(
            (f"charge-{name}", "modify_dice_roll", {"roll_type": "charge", "delta": delta})
            for name, delta in (("penalty", -1), ("bonus", 1))
        )
    else:
        specifications.extend(
            (
                (
                    "movement-penalty",
                    "modify_characteristic",
                    {"characteristic": "movement", "delta": -2},
                ),
                ("advance-penalty", "modify_dice_roll", {"roll_type": "advance", "delta": -1}),
            )
        )
    specifications.extend(
        (f"charge-extra-{index:02d}", "modify_dice_roll", {"roll_type": "charge", "delta": 1})
        for index in range(extra_charge_modifiers)
    )
    for name, kind, parameters in specifications:
        effect = generic_effect(
            effect_id=f"test:modifier-ignore:{name}",
            owner_player_id="player-a",
            target_unit_instance_ids=(UNIT_ID,),
            target_kind="this_unit",
            effect_kind=kind,
            parameters=parameters,
        )
        payload = cast(dict[str, JsonValue], effect.effect_payload)
        context = cast(dict[str, JsonValue], payload["context"])
        state.record_persisting_effect(
            replace(
                effect,
                started_phase=phase,
                effect_payload={**payload, "context": {**context, "phase": phase.value}},
                expiration=EffectExpiration.end_phase(
                    battle_round=1, phase=phase, player_id="player-a"
                ),
            )
        )
    return LocalGameSession(lifecycle=GameLifecycle.from_payload(lifecycle.to_payload()))


def submit_option(session: LocalGameSession, request: DecisionRequest, option_id: str) -> None:
    status = session.submit_option(
        request_id=request.request_id,
        option_id=option_id,
        result_id=f"{request.request_id}:selected",
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status


def start_modifier_action(session: LocalGameSession) -> DecisionRequest:
    request = pending_request(session)
    submit_option(session, request, UNIT_ID)
    request = pending_request(session)
    if request.decision_type == "select_modifier_ignores":
        return request
    if request.decision_type == "select_movement_action":
        option = next(
            option
            for option in request.options
            if isinstance(option.payload, dict)
            and option.payload.get("movement_phase_action") == "advance"
        )
        submit_option(session, request, option.option_id)
    else:
        assert request.decision_type == "select_charge_targets", request
        option = next(
            option
            for option in request.options
            if isinstance(option.payload, dict)
            and option.payload.get("target_ids") == ["army-beta:enemy"]
        )
        submit_option(session, request, option.option_id)
    request = pending_request(session)
    assert request.decision_type == "select_modifier_ignores", request
    return request


def finish_modifier_choices(
    session: LocalGameSession, ignored_ids: tuple[str, ...]
) -> DecisionRequest:
    for _ in range(30):
        request = pending_request(session)
        if request.decision_type != "select_modifier_ignores":
            return request
        assert isinstance(request.payload, dict)
        decided = cast(list[str], request.payload["decided_modifier_ids"])
        inventory = cast(list[dict[str, JsonValue]], request.payload["modifiers"])
        current = cast(dict[str, JsonValue], inventory[len(decided)]["operation"])["modifier_id"]
        prefix = "ignore" if current in ignored_ids else "keep"
        option = next(
            (option for option in request.options if option.option_id.startswith(f"{prefix}:")),
            None,
        )
        submit_option(
            session, request, f"{prefix}-remaining" if option is None else option.option_id
        )
    raise AssertionError("Modifier evaluation did not complete.")
