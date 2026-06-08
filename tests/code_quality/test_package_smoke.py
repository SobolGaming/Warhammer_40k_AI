from importlib.resources import files

from warhammer40k_core import __version__


def test_package_imports() -> None:
    assert __version__ == "0.1.0"


def test_package_declares_inline_types() -> None:
    assert files("warhammer40k_core").joinpath("py.typed").is_file()
