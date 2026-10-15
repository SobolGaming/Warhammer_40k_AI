"""Reuse immutable proposal tokens only for freshly reread, byte-identical source."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class _SourceTokens:
    content: bytes
    tokens: tuple[str, ...]


class ProposalSourceIndex:
    """Keep one entry per file in the latest successful scan, scoped to this instance."""

    def __init__(self) -> None:
        self._entries: dict[Path, _SourceTokens] = {}

    def tokens(self, paths: tuple[Path, ...]) -> tuple[str, ...]:
        current: dict[Path, _SourceTokens] = {}
        values: set[str] = set()
        for path in paths:
            identity = path.resolve()
            content = path.read_bytes()
            entry = self._entries.get(identity)
            if entry is None or entry.content != content:
                entry = _SourceTokens(content, _proposal_tokens(content, filename=str(path)))
            current[identity] = entry
            values.update(entry.tokens)
        # A failed read/decode/parse never publishes a partial index or a stale answer.
        # Replacing the inventory drops removed files, old roots and prior byte versions.
        self._entries = current
        return tuple(sorted(values))


def _proposal_tokens(content: bytes, *, filename: str) -> tuple[str, ...]:
    # Match Path.read_text(encoding="utf-8") universal-newline behavior exactly.
    source = content.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    tree = ast.parse(source, filename=filename)
    values: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            value = _string_constant(node.value)
            if value is None:
                continue
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.endswith(
                    ("_PROPOSAL_KIND", "_PROPOSAL_PAYLOAD_KIND")
                ):
                    values.add(value)
        if isinstance(node, ast.ClassDef) and node.name == "ProposalKind":
            for item in node.body:
                if isinstance(item, ast.Assign):
                    value = _string_constant(item.value)
                    if value is not None:
                        values.add(value)
    return tuple(sorted(values))


def _string_constant(node: ast.expr | None) -> str | None:
    if not isinstance(node, ast.Constant) or type(node.value) is not str:
        return None
    return node.value
