"""Native melee declaration boundary without Pile In, Charge, or game construction."""

from dataclasses import replace
from typing import cast

from tests.support.section02_fixtures import LORD_EXULTANT, Section02Definitions
from tests.support.section03_fixtures import placement, scenario
from tests.support.section04_fixtures import combat_state

from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.fight_resolution import (
    MeleeDeclarationProposal,
    MeleeDeclarationProposalRequest,
)
from warhammer40k_core.engine.fight_weapon_selection import (
    MeleeTargetAllocation,
    MeleeWeaponDeclaration,
    available_melee_weapons_payloads,
)
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.geometry.pose import Pose


def melee_case(
    d: Section02Definitions, *, datasheet: str = LORD_EXULTANT
) -> tuple[GameState, MeleeDeclarationProposalRequest, MeleeDeclarationProposal]:
    unit = d.unit(datasheet)
    state = combat_state(d, unit, phase=BattlePhase.FIGHT, distance=2.5)
    other = d.unit(LORD_EXULTANT, army_id="enemy", identity="other")
    state.army_definitions[:] = [
        replace(a, units=(*a.units, other)) if a.player_id == "opponent" else a
        for a in state.army_definitions
    ]
    assert state.battlefield_state is not None
    state.replace_battlefield_state(
        replace(
            state.battlefield_state,
            placed_armies=tuple(
                replace(
                    a,
                    unit_placements=(
                        *a.unit_placements,
                        placement(other, (Pose.at(7.5, 10),), enemy=True),
                    ),
                )
                if a.player_id == "opponent"
                else a
                for a in state.battlefield_state.placed_armies
            ),
        )
    )
    rows = available_melee_weapons_payloads(
        scenario=scenario(state),
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        unit=unit,
        army_catalog=d.package.army_catalog,
        state=state,
        source_decision_result_id="section04:activation",
    )
    request = MeleeDeclarationProposalRequest(
        "section04:melee",
        "owner",
        state.game_id,
        1,
        "owner",
        unit.unit_instance_id,
        "section04:select",
        "section04:activation",
        state.ruleset_descriptor_hash,
        rows,
        ("enemy:other", "enemy:target"),
    )
    row = cast(dict[str, JsonValue], rows[0])
    declaration = MeleeWeaponDeclaration(
        attacker_model_instance_id=cast(str, row["model_instance_id"]),
        wargear_id=cast(str, row["wargear_id"]),
        weapon_profile_id=cast(str, row["weapon_profile_id"]),
        weapon_instance_id=cast(str, row["weapon_instance_id"]),
        target_allocations=(MeleeTargetAllocation("enemy:target"),),
    )
    proposal = MeleeDeclarationProposal(
        request.request_id,
        request.proposal_kind,
        "owner",
        1,
        unit.unit_instance_id,
        request.source_decision_request_id,
        request.source_decision_result_id,
        (declaration,),
    )
    return state, request, proposal
