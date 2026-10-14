"""Real native pool inputs for explicitly qualified applicability-owner controls."""

# This fixture reads the lifecycle's existing runtime bundle, as dispatch does.
# pyright: reportPrivateUsage=false
from typing import cast

from tests.order135_gathered_step_helpers import native_gathered_shooting_request
from tests.phase13b_shooting_declaration_helpers import proposal_from_request
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.attack_sequence_state import AttackSequence
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry


def native_two_bearer_inputs() -> tuple[LocalGameSession, AttackSequence, RuntimeModifierRegistry]:
    session, request = native_gathered_shooting_request()
    proposal = proposal_from_request(
        request=request, target_unit_id="army-beta:scalar"
    ).to_payload()
    offered = cast(
        dict[str, JsonValue], cast(dict[str, JsonValue], request.payload)["proposal_request"]
    )
    weapons = cast(list[dict[str, JsonValue]], offered["available_weapons"])
    first = proposal["declarations"][0]
    matching = [
        weapon for weapon in weapons if weapon["weapon_profile_id"] == first["weapon_profile_id"]
    ]
    proposal["declarations"] = [
        {
            **first,
            "attacker_model_instance_id": cast(str, weapon["model_instance_id"]),
            "weapon_instance_id": cast(str, weapon["weapon_instance_id"]),
        }
        for weapon in matching[:2]
    ]
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="s25:owner-inputs",
        payload=validate_json_value(proposal),
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status
    state = session.lifecycle.state
    assert state is not None
    shooting = state.shooting_phase_state
    assert shooting is not None
    original = shooting.attack_sequence
    assert original is not None
    assert len(original.attack_pools) == 2
    sequence = AttackSequence.start(
        sequence_id="s25:qualified-owner-query",
        attacker_player_id=original.attacker_player_id,
        attacking_unit_instance_id=original.attacking_unit_instance_id,
        attack_pools=original.attack_pools,
    )
    registry = session.lifecycle._require_runtime_content_bundle().runtime_modifier_registry
    return session, sequence, registry
