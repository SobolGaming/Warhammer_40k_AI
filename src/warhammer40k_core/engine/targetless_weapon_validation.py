"""Validate weapon-only selection against the offered physical inventory."""

from __future__ import annotations

from warhammer40k_core.core.weapon_profiles import WeaponProfile
from warhammer40k_core.engine.ability_instance_selection import WeaponInstanceSelectionError
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.shooting_types import ShootingType
from warhammer40k_core.engine.targetless_weapons import TargetlessWeapon
from warhammer40k_core.engine.weapon_declaration import (
    AvailableWeaponPayload,
    ShootingDeclarationProposal,
    ShootingProposalValidationResult,
    WeaponDeclaration,
)


def validate_targetless_weapon(
    *,
    declaration: WeaponDeclaration,
    weapon_profile: WeaponProfile,
    proposal: ShootingDeclarationProposal,
    pending_request: DecisionRequest | None,
    selected_type: ShootingType | None,
) -> TargetlessWeapon | ShootingProposalValidationResult:
    def invalid(code: str, message: str) -> ShootingProposalValidationResult:
        return ShootingProposalValidationResult.invalid(
            proposal_request_id=proposal.proposal_request_id,
            violation_code=code,
            message=message,
            field="declarations",
        )

    if declaration.shooting_type is not (
        ShootingType.NORMAL if selected_type is None else selected_type
    ):
        return invalid(
            "shooting_type_unavailable",
            "Targetless weapon selection must retain the selected shooting type.",
        )
    if pending_request is not None:
        payload = pending_request.payload
        if not isinstance(payload, dict) or not isinstance(payload.get("proposal_request"), dict):
            return invalid(
                "weapon_inventory_drift", "Targetless weapon selection lacks its request inventory."
            )
        context = payload["proposal_request"]
        assert isinstance(context, dict)
        rows = context.get("available_weapons")
        if not isinstance(rows, list) or not any(
            isinstance(row, dict)
            and row.get("weapon_instance_id") == declaration.weapon_instance_id
            and row.get("model_instance_id") == declaration.attacker_model_instance_id
            and row.get("wargear_id") == declaration.wargear_id
            and row.get("weapon_profile_id") == declaration.weapon_profile_id
            and row.get("weapon_profile") == validate_json_value(weapon_profile.to_payload())
            and row.get("firing_deck_source_unit_instance_id")
            == declaration.firing_deck_source_unit_instance_id
            and row.get("firing_deck_source_model_instance_id")
            == declaration.firing_deck_source_model_instance_id
            for row in rows
        ):
            return invalid(
                "weapon_inventory_drift", "Targetless weapon inventory changed after the request."
            )
    try:
        return TargetlessWeapon(declaration, weapon_profile)
    except WeaponInstanceSelectionError as exc:
        return invalid("weapon_ability_selection_invalid", str(exc))


def targetless_candidates(
    *,
    weapons: list[AvailableWeaponPayload],
    actor_id: str,
    request_id: str,
    shooting_type: ShootingType,
) -> list[JsonValue]:
    from warhammer40k_core.engine.ability_instance_selection import (
        weapon_instance_groups,
        weapon_instance_selection_requests,
    )
    from warhammer40k_core.engine.interaction_metadata import (
        interaction_annotated_decision_request_payload,
    )

    return [
        validate_json_value(
            {
                **weapon,
                "target_unit_instance_id": None,
                "shooting_type": shooting_type.value,
                "required_weapon_ability_selections": [
                    interaction_annotated_decision_request_payload(request)
                    for request in weapon_instance_selection_requests(
                        WeaponProfile.from_payload(weapon["weapon_profile"]),
                        actor_id=actor_id,
                        request_id=(
                            f"{request_id}:targetless:{weapon['weapon_instance_id']}:"
                            f"{weapon['weapon_profile_id']}"
                        ),
                        source_context={
                            "weapon_instance_id": weapon["weapon_instance_id"],
                            "target_unit_instance_id": None,
                        },
                    )
                ],
            }
        )
        for weapon in weapons
        if any(
            len(sources) > 1
            for _, sources in weapon_instance_groups(
                WeaponProfile.from_payload(weapon["weapon_profile"])
            )
        )
    ]
