from warhammer40k_core import __version__


def test_quality_gate_placeholder() -> None:
    # Replace with no-broad-exceptions / no-fallback / import-boundary audits in the first PR.
    assert __version__ == "0.1.0"
