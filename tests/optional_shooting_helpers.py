"""Facade helpers for optional target selection regressions."""

from __future__ import annotations

from typing import cast

from tests.empty_shooting_helpers import SHOOTER
from tests.phase13b_shooting_declaration_helpers import _proposal_from_request
from tests.psychic_modifier_helpers import pending_request, submit_fixture_request
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id


def select_optional_shooting(session: LocalGameSession, kind: str = "normal") -> DecisionRequest:
    request = session.advance_until_decision_or_terminal().decision_request
    assert request is not None
    state = session.lifecycle.state
    assert state is not None
    request = session.submit_option(
        request_id=request.request_id,
        option_id=rules_unit_view_by_id(state=state, unit_instance_id=SHOOTER).unit_instance_id,
        result_id="order95:unit",
    ).decision_request
    assert request is not None
    request = session.submit_option(
        request_id=request.request_id, option_id=kind, result_id="order95:type"
    ).decision_request
    assert request is not None
    assert request.decision_type == "submit_shooting_declaration"
    return request


def optional_payload(
    request: DecisionRequest, *, all_targetless: bool = True
) -> dict[str, JsonValue]:
    assert isinstance(request.payload, dict)
    context = request.payload["proposal_request"]
    assert isinstance(context, dict)
    candidates = context["target_candidates"]
    assert isinstance(candidates, list)
    target = next(
        row["target_unit_instance_id"]
        for row in candidates
        if isinstance(row, dict) and row["is_legal"]
    )
    assert isinstance(target, str)
    proposal = _proposal_from_request(request=request, target_unit_id=target)
    payload = cast(dict[str, JsonValue], validate_json_value(proposal.to_payload()))
    rows = payload["declarations"]
    assert isinstance(rows, list)
    # Include every own physical weapon; the baseline declaration fixture selects only one.
    weapons = context["available_weapons"]
    assert isinstance(weapons, list)
    assert isinstance(rows[0], dict)
    prototype = rows[0]
    rows[:] = [
        {
            **prototype,
            "attacker_model_instance_id": weapon["model_instance_id"],
            "weapon_instance_id": weapon["weapon_instance_id"],
            "wargear_id": weapon["wargear_id"],
            "weapon_profile_id": weapon["weapon_profile_id"],
        }
        for weapon in weapons
        if isinstance(weapon, dict) and "firing_deck_source_model_instance_id" not in weapon
    ]
    for index, row in enumerate(rows):
        assert isinstance(row, dict)
        if all_targetless or index == 0:
            row["target_unit_instance_id"] = None
    return payload


def finish_selected_weapons(session: LocalGameSession, result_id: str) -> None:
    for _ in range(100):
        state = session.lifecycle.state
        assert state is not None
        request = pending_request(session)
        if (
            request.decision_type == "select_shooting_unit"
            and state.out_of_phase_shooting_state is None
            and state.shooting_phase_state is not None
            and state.shooting_phase_state.attack_sequence is None
            and state.shooting_phase_state.pending_completed_attack_sequence is None
        ):
            return
        submit_fixture_request(session, request)
    raise AssertionError(f"Selected weapons did not finish: {result_id}")


def dark_pact_optional_session(*, automatic: bool, hazardous: bool) -> LocalGameSession:
    """Load the real source-backed selected-unit provider through the runtime bundle."""
    from dataclasses import replace

    from tests.chaos_defiler_catalog_helpers import july_defiler_catalog_package
    from tests.phase13b_shooting_declaration_helpers import shooting_lifecycle
    from warhammer40k_core.core.detachment import DetachmentDefinition
    from warhammer40k_core.core.faction_aliases import CHAOS_SPACE_MARINES_FACTION_ID
    from warhammer40k_core.core.weapon_profiles import WeaponKeyword

    source = july_defiler_catalog_package().army_catalog
    factions = tuple(
        replace(
            row,
            faction_id=CHAOS_SPACE_MARINES_FACTION_ID if row.faction_id == "CSM" else "death-guard",
        )
        if row.faction_id in {"CSM", "DG"}
        else row
        for row in source.factions
    )
    detachments = tuple(
        DetachmentDefinition(
            canonical_detachment_id=identifier,
            detachment_id=identifier,
            name=identifier,
            faction_id=faction,
            detachment_point_cost=1,
            unit_datasheet_ids=(unit,),
            force_disposition_ids=("purge-the-foe",),
            source_ids=("test:order95:dark-pact",),
        )
        for identifier, faction, unit in (
            ("pactbound-zealots", CHAOS_SPACE_MARINES_FACTION_ID, "000000969"),
            ("champions-of-contagion", "death-guard", "000004209"),
        )
    )
    catalog = replace(source, factions=factions, detachments=detachments)
    if automatic or hazardous:
        catalog = replace(
            catalog,
            wargear=tuple(
                replace(
                    item,
                    weapon_profiles=tuple(
                        replace(
                            profile,
                            range_profile=replace(profile.range_profile, distance_inches=1)
                            if automatic
                            else profile.range_profile,
                            keywords=tuple(sorted({*profile.keywords, WeaponKeyword.HAZARDOUS}))
                            if hazardous
                            else profile.keywords,
                            ability_sources=(),
                        )
                        if profile.range_profile.distance_inches is not None
                        else profile
                        for profile in item.weapon_profiles
                    ),
                )
                for item in catalog.wargear
            ),
        )
    lifecycle, _ = shooting_lifecycle(
        alpha_unit_ids=("defiler-attacker", "defiler-spare"),
        game_id="review95-darkpact",
        alpha_unit_specs=tuple(
            (name, "000000969", "000000969:defiler", 1)
            for name in ("defiler-attacker", "defiler-spare")
        ),
        enemy_datasheet=("000004209", "000004209:defiler", 1),
        catalog=catalog,
        alpha_faction_id=CHAOS_SPACE_MARINES_FACTION_ID,
        alpha_detachment_ids=("pactbound-zealots",),
        enemy_faction_id="death-guard",
        enemy_detachment_ids=("champions-of-contagion",),
    )
    lifecycle._require_runtime_content_bundle()  # pyright: ignore[reportPrivateUsage]
    return LocalGameSession(lifecycle)
