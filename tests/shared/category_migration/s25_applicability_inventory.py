"""Source-owner controls over real native pools and explicitly analytical bindings.

These counterfactual pure queries do not claim normal facade/provider execution
for the analytical bindings. Native positive execution is proved separately.
"""

from dataclasses import replace
from typing import cast

import pytest

from tests.d10_profile_helpers import (
    advertised_weapons,
    declaration_request,
    profile_proposal,
    profile_session,
    submit_profile,
)
from tests.s25_gathering_helpers import native_two_bearer_inputs
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.engine.attack_gathering_dependencies import AttackGatheringDependency
from warhammer40k_core.engine.attack_sequence_state import AttackSequence
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.native_attack_gathering import (
    native_gathered_attack_groups_for_target,
)
from warhammer40k_core.engine.runtime_modifiers import (
    HitRollModifierBinding,
    RuntimeModifierRegistry,
    SaveOptionModifierBinding,
    WoundRollModifierBinding,
)


@pytest.fixture(scope="module")
def inputs() -> tuple[LocalGameSession, AttackSequence, RuntimeModifierRegistry]:
    return native_two_bearer_inputs()


def group_count(
    inputs: tuple[LocalGameSession, AttackSequence, RuntimeModifierRegistry],
    registry: RuntimeModifierRegistry,
    sequence: AttackSequence | None = None,
) -> int:
    session, base, _ = inputs
    state = session.lifecycle.state
    assert state is not None
    before = session.to_persistence_payload()
    groups = native_gathered_attack_groups_for_target(
        state=state,
        registry=registry,
        attack_sequence=base if sequence is None else sequence,
        target_unit_instance_id=base.attack_pools[0].target_unit_instance_id,
        target_has_character=False,
        has_custom_callbacks=False,
    )
    assert session.to_persistence_payload() == before
    return len(groups)


__all__: list[str] = []
__all__ += ["AttackGatheringDependency", "AttackSequence", "Characteristic"]
__all__ += ["CharacteristicValue", "HitRollModifierBinding", "JsonValue", "LocalGameSession"]
__all__ += ["RuntimeModifierRegistry", "SaveOptionModifierBinding", "WoundRollModifierBinding"]
__all__ += ["advertised_weapons", "cast", "declaration_request", "group_count", "inputs"]
__all__ += ["native_gathered_attack_groups_for_target", "native_two_bearer_inputs"]
__all__ += ["profile_proposal", "profile_session", "pytest", "replace", "submit_profile"]
