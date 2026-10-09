"""Real-domain random melee fixtures shared by regressions and diagnostics."""

from __future__ import annotations

from dataclasses import replace
from typing import cast

from tests.phase15c_fight_order_helpers import drain_fight_movement_requests, fight_lifecycle
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.dice import DiceExpression
from warhammer40k_core.core.wargear import Wargear
from warhammer40k_core.core.weapon_profiles import AbilityDescriptor, AttackProfile, WeaponKeyword
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.list_validation import AttachmentDeclaration
from warhammer40k_core.geometry.pose import Pose


def random_melee_session(
    *,
    game_id: str = "order92-random-melee",
    random: bool = True,
    extra: bool = False,
    cleave: bool = False,
    target_attached: bool = False,
    profiles: bool = False,
    attacker_models: int = 1,
    attached: bool = False,
    fixed_bodyguard: bool = False,
    fixed_attacks: int | None = None,
    pause_at_first_hit: bool = False,
) -> LocalGameSession:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    if fixed_bodyguard:
        fixed_blade = next(
            item for item in catalog.wargear if item.wargear_id == "core-leader-blade"
        ).weapon_profiles[0]
        catalog = replace(
            catalog,
            wargear=tuple(
                replace(
                    item,
                    weapon_profiles=(replace(fixed_blade, profile_id="core-bolt-rifle:standard"),),
                )
                if item.wargear_id == "core-bolt-rifle"
                else item
                for item in catalog.wargear
            ),
        )
    if random:
        catalog = replace(
            catalog,
            wargear=tuple(
                replace(
                    item,
                    weapon_profiles=tuple(
                        replace(profile, attack_profile=AttackProfile.dice(DiceExpression(1, 6)))
                        for profile in item.weapon_profiles
                    ),
                )
                if item.wargear_id == "core-leader-blade"
                else item
                for item in catalog.wargear
            ),
        )
    blade = next(item for item in catalog.wargear if item.wargear_id == "core-leader-blade")
    primary = blade.weapon_profiles[0]
    if fixed_attacks is not None:
        primary = replace(primary, attack_profile=AttackProfile.fixed(fixed_attacks))
    if cleave:
        primary = replace(
            primary, keywords=(WeaponKeyword.CLEAVE,), abilities=(AbilityDescriptor.cleave(2),)
        )
    blade = replace(blade, weapon_profiles=(primary,))
    if profiles:
        blade = replace(
            blade,
            weapon_profiles=(primary, replace(primary, profile_id="core-leader-blade:alternate")),
        )
    gear = [blade if item.wargear_id == blade.wargear_id else item for item in catalog.wargear]
    if extra:
        gear.append(
            Wargear(
                wargear_id="order92-extra",
                name="Extra weapon",
                weapon_profiles=(
                    replace(
                        primary,
                        profile_id="order92-extra:standard",
                        keywords=(WeaponKeyword.EXTRA_ATTACKS,),
                        abilities=(),
                    ),
                ),
            )
        )
    catalog = replace(
        catalog,
        wargear=tuple(gear),
        datasheets=tuple(
            replace(
                sheet,
                composition=tuple(
                    replace(row, min_models=1, max_models=max(1, attacker_models))
                    for row in sheet.composition
                ),
                wargear_options=tuple(
                    replace(
                        row,
                        default_wargear_ids=(*row.default_wargear_ids, "order92-extra"),
                        allowed_wargear_ids=(*row.allowed_wargear_ids, "order92-extra"),
                        min_selections=2,
                        max_selections=2,
                    )
                    if extra
                    else row
                    for row in sheet.wargear_options
                ),
            )
            if sheet.datasheet_id == "core-character-leader"
            else sheet
            for sheet in catalog.datasheets
        ),
    )
    if target_attached:
        catalog = replace(
            catalog,
            datasheets=tuple(
                replace(
                    sheet,
                    composition=tuple(replace(row, min_models=4) for row in sheet.composition),
                )
                if sheet.datasheet_id == "core-intercessor-like-infantry"
                else sheet
                for sheet in catalog.datasheets
            ),
        )
    lifecycle, _ = fight_lifecycle(
        alpha_unit_ids=("attacker", "bodyguard") if attached else ("attacker",),
        alpha_attachment_declarations=(
            AttachmentDeclaration(
                source_unit_selection_id="attacker",
                bodyguard_unit_selection_id="bodyguard",
            ),
        )
        if attached
        else (),
        enemy_unit_ids=("target-a", "target-b"),
        origins={
            "attacker": Pose.at(20, 20),
            "bodyguard": Pose.at(21, 18.5),
            "target-a": Pose.at(22, 20),
            "target-b": Pose.at(20, 22),
        },
        game_id=game_id,
        catalog=catalog,
        datasheet_id="core-character-leader",
        model_profile_id="core-character-leader",
        model_count=1,
        alpha_unit_specs={
            "attacker": ("core-character-leader", "core-character-leader", attacker_models),
            **(
                {"bodyguard": ("core-intercessor-like-infantry", "core-intercessor-like", 5)}
                if attached
                else {}
            ),
        },
        enemy_unit_specs=None
        if not cleave
        else {
            "target-a": (
                "core-intercessor-like-infantry",
                "core-intercessor-like",
                4 if target_attached else 5,
            ),
            "target-b": ("core-character-leader", "core-character-leader", 1),
        },
        enemy_attachment_declarations=(
            AttachmentDeclaration(
                source_unit_selection_id="target-b", bodyguard_unit_selection_id="target-a"
            ),
        )
        if target_attached
        else (),
        fights_first_unit_keys=("bodyguard",) if attached else ("attacker",),
        record_deployment=True,
    )
    if pause_at_first_hit:
        from warhammer40k_core.engine.command_points import CommandPointSourceKind

        state = lifecycle.state
        assert state is not None
        state.gain_command_points(
            player_id="player-a",
            amount=1,
            source_id="order113-cleave-pending-hit",
            source_kind=CommandPointSourceKind.OTHER,
            cap_exempt=True,
        )
    return LocalGameSession(lifecycle)


def melee_boundary(session: LocalGameSession) -> DecisionRequest:
    status = session.advance_until_decision_or_terminal()
    for index in range(40):
        status = drain_fight_movement_requests(session.lifecycle, status)
        request = status.decision_request
        assert request is not None
        if request.decision_type in {"submit_melee_declaration", "select_melee_weapon"}:
            return request
        if request.decision_type == "submit_stratagem_target_proposal":
            from warhammer40k_core.engine.stratagems_requests import stratagem_decline_payload

            status = session.submit_parameterized_payload(
                request_id=request.request_id,
                result_id=f"prepare-{index}",
                payload=stratagem_decline_payload(),
            )
            continue
        option = next(
            option for option in request.options if not option.option_id.startswith("complete")
        )
        status = session.submit_option(
            request_id=request.request_id, option_id=option.option_id, result_id=f"prepare-{index}"
        )
    raise AssertionError("Melee declaration boundary was not reached.")


def declaration_payload(request: DecisionRequest) -> dict[str, JsonValue]:
    body = cast(dict[str, JsonValue], request.payload)
    proposal = cast(dict[str, JsonValue], body["proposal_request"])
    return {
        "proposal_request_id": request.request_id,
        "proposal_kind": "melee_declaration",
        "player_id": request.actor_id,
        **{
            key: proposal[key]
            for key in (
                "battle_round",
                "unit_instance_id",
                "source_decision_request_id",
                "source_decision_result_id",
            )
        },
        "declarations": [],
    }


def single_target_commitment_payload(request: DecisionRequest) -> dict[str, JsonValue]:
    payload = declaration_payload(request)
    proposal = cast(
        dict[str, JsonValue], cast(dict[str, JsonValue], request.payload)["proposal_request"]
    )
    rows = cast(list[dict[str, JsonValue]], proposal["available_weapons"])
    payload["declarations"] = [
        {
            "attacker_model_instance_id": row["model_instance_id"],
            **{key: row[key] for key in ("wargear_id", "weapon_instance_id", "weapon_profile_id")},
            "target_allocations": [
                {
                    "target_unit_instance_id": cast(
                        list[JsonValue], row["engaged_target_unit_instance_ids"]
                    )[0]
                }
            ],
        }
        for row in rows
    ]
    return payload
