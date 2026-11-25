"""Authenticate the Cavalcade receipt addition before historical policy proofs."""

from __future__ import annotations

import hashlib

_POLICY_AFTER = "6da5eb9e49bb2e521afe322cae620dde2e40162fbdc7605326cde2d28f0dbf6c"
_POLICY_BEFORE = "1f08fa40369b152857671482a20772bbbb94fdcb09a3b1f158435de1e649a67a"
_PRIVATE_RNG_AFTER = "13c53fe42ddfd21f6dad80a0e93c0e58afe5fb99b32ccfdb860ace0c4856ba71"
_PRIVATE_RNG_BEFORE = "62db9db823b80edcdcfa911ebb9008aa273da65534066292bef8fc183201837d"
_POLICY_START = b'    registered_fixture = specification.get("registered_full_game_fixture")\n'
_POLICY_END = b"    if campaign.required("


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def cavalcade_policy_predecessor(raw: bytes) -> bytes:
    """Recover the exact historical policy before its registered-fixture block."""
    from tools.performance_dark_pacts import dark_pacts_policy_predecessor
    from tools.performance_fools_flight import fools_flight_policy_predecessor

    raw = dark_pacts_policy_predecessor(fools_flight_policy_predecessor(raw))
    if _digest(raw) != _POLICY_AFTER:
        return raw
    start = raw.index(_POLICY_START)
    end = raw.index(_POLICY_END, start)
    predecessor = raw[:start] + raw[end:]
    if _digest(predecessor) != _POLICY_BEFORE:
        raise ValueError("Cavalcade receipt policy predecessor drifted.")
    return predecessor


def cavalcade_private_rng_predecessor(raw: bytes) -> bytes:
    """Recover the exact source pinned by the original private RNG receipt."""
    if _digest(raw) != _PRIVATE_RNG_AFTER:
        return raw
    raw = raw.replace(
        b"\nfrom tools.performance_cavalcade_policy_successor import (\n"
        b"    cavalcade_policy_predecessor,\n"
        b"    cavalcade_private_rng_predecessor,\n"
        b")\n",
        b"",
        1,
    )
    raw = raw.replace(
        b"    module_bytes = cavalcade_private_rng_predecessor(Path(__file__).read_bytes())\n",
        b"",
        1,
    )
    raw = raw.replace(
        b'        or scope["module_sha256"] != _hash(module_bytes)\n',
        b'        or scope["module_sha256"] != _hash(Path(__file__).read_bytes())\n',
        1,
    )
    raw = raw.replace(b"    raw = cavalcade_policy_predecessor(raw)\n", b"", 1)
    if _digest(raw) != _PRIVATE_RNG_BEFORE:
        raise ValueError("Cavalcade private RNG policy predecessor drifted.")
    return raw
