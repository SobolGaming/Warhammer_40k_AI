"""Movement-budget policy admission and Linux envelope identity."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from typing import cast

import pytest

from warhammer40k_core.adapters.execution_profile import (
    PROFILE_SCHEMA,
    ExecutionProfileError,
    checkpoint_bytes,
    checkpoint_envelope,
    content_hash,
    numerical_policy_for_profile,
    validate_executor_profile,
)
from warhammer40k_core.adapters.linux_authority_transport import LinuxAuthority
from warhammer40k_core.adapters.linux_authority_worker import LinuxAuthorityDispatcher
from warhammer40k_core.adapters.numerical_policy import (
    CURRENT_NUMERICAL_POLICY_ID,
    NumericalPolicyConfiguration,
    NumericalPolicyError,
)
from warhammer40k_core.engine.event_log import JsonValue


@pytest.mark.parametrize("policy_id", ["milli-inch-half-away-v1", "unknown", "", None, True, 1])
def test_unknown_or_inactive_numerical_policy_is_never_executed(policy_id: object) -> None:
    with pytest.raises(NumericalPolicyError, match="Unsupported numerical policy"):
        NumericalPolicyConfiguration(cast(str, policy_id))
    profile: dict[str, JsonValue] = {
        "schema_version": PROFILE_SCHEMA,
        "engine_build_id": "test-build",
        "numerical_policy_id": cast(JsonValue, policy_id),
    }
    with pytest.raises(ExecutionProfileError, match="numerical policy"):
        validate_executor_profile(profile, expected=profile, engine_build_id="test-build")
    with pytest.raises(ExecutionProfileError, match="numerical policy"):
        LinuxAuthorityDispatcher(profile)
    # An invalid executable proves policy admission happens before process launch.
    with pytest.raises(ExecutionProfileError, match="numerical policy"):
        LinuxAuthority(["must-not-launch-an-executor"], expected_profile=profile)


def test_missing_policy_and_retained_profile_require_their_original_executor() -> None:
    for profile in (
        {"schema_version": PROFILE_SCHEMA, "engine_build_id": "test-build"},
        {"schema_version": "linux-execution-profile-v1", "engine_build_id": "test-build"},
    ):
        with pytest.raises(ExecutionProfileError):
            numerical_policy_for_profile(cast(JsonValue, profile))
        with pytest.raises(ExecutionProfileError):
            LinuxAuthorityDispatcher(cast(JsonValue, profile))
    # The byte utility remains able to preserve historical evidence unchanged;
    # preservation is separate from permission to execute it on this runtime.
    raw = b'{ "distance": 0.2500000000000031, "signed_zero": -0.0 }\n'
    old_profile: JsonValue = {"schema_version": "linux-execution-profile-v1"}
    envelope = checkpoint_envelope(
        payload_bytes=raw, profile=old_profile, provenance={"kind": "retained-original"}
    )
    assert checkpoint_bytes(envelope, profile=old_profile) == raw


def test_policy_configuration_and_checkpoint_cache_identity_are_explicit() -> None:
    policy = NumericalPolicyConfiguration()
    assert policy.numerical_policy_id == CURRENT_NUMERICAL_POLICY_ID
    with pytest.raises(FrozenInstanceError):
        policy.__setattr__("numerical_policy_id", "milli-inch-half-away-v1")
    first = policy.checkpoint_cache_identity(
        execution_profile_hash="profile-a", inner_checkpoint_hash="state-a"
    )
    assert first == (CURRENT_NUMERICAL_POLICY_ID, "profile-a", "state-a")
    assert first != policy.checkpoint_cache_identity(
        execution_profile_hash="profile-b", inner_checkpoint_hash="state-a"
    )
    assert first != policy.checkpoint_cache_identity(
        execution_profile_hash="profile-a", inner_checkpoint_hash="state-b"
    )
    profile: dict[str, JsonValue] = {
        "schema_version": PROFILE_SCHEMA,
        "numerical_policy_id": CURRENT_NUMERICAL_POLICY_ID,
    }
    dispatcher = LinuxAuthorityDispatcher(profile)
    before = dispatcher.profile
    profile["numerical_policy_id"] = "milli-inch-half-away-v1"
    assert dispatcher.profile == before
    assert content_hash(profile) != content_hash(before)
    with pytest.raises(ExecutionProfileError, match="configuration"):
        LinuxAuthority(
            ["must-not-launch-an-executor"],
            expected_profile=before,
            numerical_policy=cast(NumericalPolicyConfiguration, None),
        )
