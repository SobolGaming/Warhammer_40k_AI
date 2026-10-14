"""Infrastructure contract-source discovery: exact inputs, reuse and fresh failures."""

from __future__ import annotations

import ast
import json
import os
import runpy
import subprocess
import sys
from pathlib import Path
from types import FunctionType
from typing import cast

import pytest
from scripts.proposal_source_index import ProposalSourceIndex


@pytest.fixture
def parsed_files(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    original = ast.parse
    calls: list[str] = []

    def counted(source: str, *, filename: str) -> ast.Module:
        calls.append(filename)
        return original(source, filename=filename)

    monkeypatch.setattr("scripts.proposal_source_index.ast.parse", counted)
    return calls


def test_source_index_preserves_literal_proposal_grammar(tmp_path: Path) -> None:
    source = tmp_path / "source.py"
    source.write_text(
        """A_PROPOSAL_KIND = OTHER_PROPOSAL_PAYLOAD_KIND = "shared"
UNRELATED = "ignore"
ANNOTATED_PROPOSAL_KIND: str = "ignore"
NUMBER_PROPOSAL_KIND = 1
COMPUTED_PROPOSAL_KIND = "no" + "pe"
class ProposalKind:
    VALUE = "enum"
    ALIAS = VALUE
    ANNOTATED: str = "ignore"
    NUMBER = 2
class Other:
    VALUE = "ignore"
def nested():
    HIDDEN_PROPOSAL_KIND = "ignore"
""",
        encoding="utf-8",
    )
    assert ProposalSourceIndex().tokens((source,)) == ("enum", "shared")


def test_identical_bytes_reuse_tokens_but_fresh_instances_parse(
    tmp_path: Path, parsed_files: list[str]
) -> None:
    source = tmp_path / "source.py"
    source.write_text('A_PROPOSAL_KIND = "first"\n', encoding="utf-8")
    index = ProposalSourceIndex()
    assert index.tokens((source,)) == ("first",)
    assert index.tokens((source,)) == ("first",)
    assert parsed_files == [str(source)]
    assert ProposalSourceIndex().tokens((source,)) == ("first",)
    assert parsed_files == [str(source), str(source)]


def test_byte_change_with_same_size_and_mtime_invalidates(
    tmp_path: Path, parsed_files: list[str]
) -> None:
    source = tmp_path / "source.py"
    source.write_bytes(b'A_PROPOSAL_KIND = "one"\n')
    original = source.stat()
    index = ProposalSourceIndex()
    assert index.tokens((source,)) == ("one",)
    source.write_bytes(b'A_PROPOSAL_KIND = "two"\n')
    os.utime(source, ns=(original.st_atime_ns, original.st_mtime_ns))
    assert source.stat().st_size == original.st_size
    assert source.stat().st_mtime_ns == original.st_mtime_ns
    assert index.tokens((source,)) == ("two",)
    assert parsed_files == [str(source), str(source)]


def test_current_inventory_adds_removes_and_drops_previous_roots(
    tmp_path: Path, parsed_files: list[str]
) -> None:
    first = tmp_path / "first.py"
    second = tmp_path / "second.py"
    first.write_text('A_PROPOSAL_KIND = "first"\n', encoding="utf-8")
    second.write_text('B_PROPOSAL_KIND = "second"\n', encoding="utf-8")
    index = ProposalSourceIndex()
    assert index.tokens((first,)) == ("first",)
    assert index.tokens((first, second)) == ("first", "second")
    assert index.tokens((second,)) == ("second",)
    assert index.tokens((first,)) == ("first",)
    assert parsed_files == [str(first), str(second), str(first)]
    assert index.tokens(()) == ()
    assert index.tokens((first,)) == ("first",)
    assert parsed_files == [str(first), str(second), str(first), str(first)]


def test_identical_content_at_distinct_paths_retains_path_identity(
    tmp_path: Path, parsed_files: list[str]
) -> None:
    first = tmp_path / "first.py"
    second = tmp_path / "second.py"
    for source in (first, second):
        source.write_text('A_PROPOSAL_KIND = "same"\n', encoding="utf-8")
    index = ProposalSourceIndex()
    assert index.tokens((first, second)) == ("same",)
    assert parsed_files == [str(first), str(second)]


@pytest.mark.parametrize("invalid", [b"A_PROPOSAL_KIND = (", b"\xef\xbb\xbfX = 1"])
def test_warm_entry_never_hides_syntax_errors(tmp_path: Path, invalid: bytes) -> None:
    source = tmp_path / "source.py"
    source.write_text('A_PROPOSAL_KIND = "valid"\n', encoding="utf-8")
    index = ProposalSourceIndex()
    assert index.tokens((source,)) == ("valid",)
    source.write_bytes(invalid)
    with pytest.raises(SyntaxError):
        index.tokens((source,))
    with pytest.raises(SyntaxError):
        index.tokens((source,))


def test_warm_entry_never_hides_decode_or_missing_file_errors(tmp_path: Path) -> None:
    source = tmp_path / "source.py"
    source.write_text('A_PROPOSAL_KIND = "valid"\n', encoding="utf-8")
    index = ProposalSourceIndex()
    assert index.tokens((source,)) == ("valid",)
    source.write_bytes(b"\xff")
    with pytest.raises(UnicodeDecodeError):
        index.tokens((source,))
    source.unlink()
    with pytest.raises(FileNotFoundError):
        index.tokens((source,))


def test_partial_failure_does_not_publish_new_entries(
    tmp_path: Path, parsed_files: list[str]
) -> None:
    first = tmp_path / "first.py"
    second = tmp_path / "second.py"
    first.write_text('A_PROPOSAL_KIND = "old"\n', encoding="utf-8")
    second.write_text('B_PROPOSAL_KIND = "valid"\n', encoding="utf-8")
    index = ProposalSourceIndex()
    assert index.tokens((first, second)) == ("old", "valid")
    first.write_text('A_PROPOSAL_KIND = "new"\n', encoding="utf-8")
    second.write_text("B_PROPOSAL_KIND = (", encoding="utf-8")
    with pytest.raises(SyntaxError):
        index.tokens((first, second))
    second.write_text('B_PROPOSAL_KIND = "valid"\n', encoding="utf-8")
    assert index.tokens((first, second)) == ("new", "valid")
    assert parsed_files.count(str(first)) == 3


def test_results_are_immutable_and_newlines_match_text_loading(tmp_path: Path) -> None:
    source = tmp_path / "source.py"
    index = ProposalSourceIndex()
    for newline in (b"\n", b"\r\n", b"\r"):
        source.write_bytes(
            newline.join((b'A_PROPOSAL_KIND = "alpha"', b'B_PROPOSAL_KIND = "beta"'))
        )
        result = index.tokens((source,))
        assert result == ("alpha", "beta")
        changed = (*result, "caller-only")
        assert changed != index.tokens((source,))
        assert isinstance(result, tuple)


def test_fresh_processes_start_without_a_shared_index(tmp_path: Path) -> None:
    source = tmp_path / "source.py"
    source.write_text('A_PROPOSAL_KIND = "first"\n', encoding="utf-8")
    program = """
import ast, json, sys
from pathlib import Path
from scripts.proposal_source_index import ProposalSourceIndex
calls = []
original = ast.parse
def counted(source, *, filename):
    calls.append(filename)
    return original(source, filename=filename)
ast.parse = counted
index = ProposalSourceIndex()
path = Path(sys.argv[1])
first = index.tokens((path,))
assert index.tokens((path,)) == first
print(json.dumps({'tokens': first, 'parses': len(calls)}))
"""
    for token in ("first", "other"):
        source.write_text(f'A_PROPOSAL_KIND = "{token}"\n', encoding="utf-8")
        completed = subprocess.run(
            [sys.executable, "-B", "-c", program, str(source)],
            cwd=Path(__file__).resolve().parents[2],
            capture_output=True,
            text=True,
            check=True,
            timeout=15,
        )
        assert json.loads(completed.stdout) == {"tokens": [token], "parses": 1}


def test_builder_wrapper_rereads_inventory_and_changed_source_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scripts = Path(__file__).resolve().parents[2] / "scripts"
    monkeypatch.setattr(sys, "path", [str(scripts), *sys.path])
    namespace = runpy.run_path(str(scripts / "build_external_contract.py"))
    wrapper = cast(FunctionType, namespace["_proposal_kind_tokens"])
    first_root = tmp_path / "first-root"
    second_root = tmp_path / "second-root"
    first_root.mkdir()
    second_root.mkdir()
    first = first_root / "first.py"
    first.write_text('A_PROPOSAL_KIND = "first"\n', encoding="utf-8")
    monkeypatch.setitem(wrapper.__globals__, "SRC_ROOT", first_root)
    assert wrapper() == ("first",)
    first.write_text('A_PROPOSAL_KIND = "changed"\n', encoding="utf-8")
    second = first_root / "second.py"
    second.write_text('B_PROPOSAL_KIND = "added"\n', encoding="utf-8")
    assert wrapper() == ("added", "changed")
    first.rename(first_root / "renamed.py")
    second.unlink()
    assert wrapper() == ("changed",)
    (second_root / "first.py").write_text('C_PROPOSAL_KIND = "other-root"\n', encoding="utf-8")
    monkeypatch.setitem(wrapper.__globals__, "SRC_ROOT", second_root)
    assert wrapper() == ("other-root",)
    monkeypatch.setitem(wrapper.__globals__, "SRC_ROOT", first_root)
    assert wrapper() == ("changed",)
