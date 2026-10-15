"""Diagnostic only: add progress outside the unchanged original micro timing regions."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path


def main() -> None:
    # Emit before importing the larger original harness or AST tooling.
    root, output = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    if output.is_relative_to(root) or output.exists():
        raise ValueError("Diagnostic evidence needs a fresh external directory")
    output.mkdir(parents=True)
    started, cpu = time.monotonic(), time.process_time()
    sequence = 0

    def progress(phase: str) -> None:
        nonlocal sequence
        row = {
            "sequence": sequence,
            "phase": phase,
            "epoch": time.time(),
            "monotonic": time.monotonic(),
            "since_python_entry": time.monotonic() - started,
            "process_cpu_since_entry": time.process_time() - cpu,
        }
        sequence += 1
        with (output / "progress.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, allow_nan=False) + "\n")
            stream.flush()

    progress("python_entry")
    import ast
    import copy
    import hashlib
    import importlib.util

    source = Path(__file__).with_name("source_reuse_experiment.py")
    raw = source.read_bytes()
    if (
        hashlib.sha256(raw).hexdigest()
        != "1b5989d63b299de7d605b3cde95c9ee5f75bccc832b7a26844048d75bf34e0ba"
    ):
        raise ValueError("Original microbenchmark source changed")
    progress("before_original_harness_import")
    spec = importlib.util.spec_from_file_location("_original_micro_harness", source)
    if spec is None or spec.loader is None:
        raise ValueError("Original harness loader unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    progress("after_original_harness_import")
    original = next(
        n for n in ast.parse(raw).body if isinstance(n, ast.FunctionDef) and n.name == "micro"
    )
    function = copy.deepcopy(original)
    annotations = []

    def marker(label: str) -> ast.Expr:
        annotations.append(label)
        return ast.Expr(
            ast.Call(ast.Name("_diagnostic_progress", ast.Load()), [ast.Constant(label)], [])
        )

    def around(node: ast.stmt, label: str) -> list[ast.stmt]:
        return [marker("before:" + label), node, marker("after:" + label)]

    for node in function.body:
        if isinstance(node, ast.For):
            # Outer count loop: setup/GC separate, entire timed sample region intact.
            body = []
            for statement in node.body:
                if isinstance(statement, ast.For):
                    statement.body = [marker("sample_begin"), *statement.body, marker("sample_end")]
                body.extend(
                    around(
                        statement,
                        "scenario:"
                        + str(statement.lineno)
                        + ":"
                        + ast.unparse(statement).splitlines()[0][:100],
                    )
                )
            node.body = body
        elif isinstance(node, ast.Try):
            node.body = [
                part
                for statement in node.body
                for part in around(statement, "work_count:" + str(statement.lineno))
            ]
    function.body = [
        part
        for statement in function.body
        for part in around(
            statement,
            "micro:" + str(statement.lineno) + ":" + ast.unparse(statement).splitlines()[0][:100],
        )
    ]

    class RemoveMarkers(ast.NodeTransformer):
        def visit_Expr(self, node: ast.Expr) -> ast.AST | None:
            if (
                isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Name)
                and node.value.func.id == "_diagnostic_progress"
            ):
                return None
            return self.generic_visit(node)

    restored = RemoveMarkers().visit(copy.deepcopy(function))
    if ast.dump(restored, include_attributes=False) != ast.dump(original, include_attributes=False):
        raise ValueError("Diagnostic changed original workload statements")
    old_inner = [n for n in ast.walk(original) if isinstance(n, ast.For)][1]
    new_inner = [n for n in ast.walk(function) if isinstance(n, ast.For)][1]
    if [ast.dump(n) for n in new_inner.body[1:-1]] != [ast.dump(n) for n in old_inner.body]:
        raise ValueError("Diagnostic inserted work inside the original timed sample region")
    proof = {
        "original_micro_ast_sha256": hashlib.sha256(ast.dump(original).encode()).hexdigest(),
        "original_source_sha256": hashlib.sha256(raw).hexdigest(),
        "complete_original_ast_preserved_after_removing_only_progress_calls": True,
        "sample_loop_body_unchanged_between_outer_progress_markers": True,
        "progress_labels": annotations,
        "qualification": (
            "Diagnostic only; progress I/O changes inter-sample context. "
            "Never numerical acceptance evidence."
        ),
    }
    (output / "instrumentation.json").write_text(
        json.dumps(proof, indent=2) + "\n", encoding="utf-8"
    )
    if len(sys.argv) == 4 and sys.argv[3] == "--verify-only":
        progress("static_verification_complete_no_micro_executed")
        return
    namespace = vars(module)
    namespace["_diagnostic_progress"] = progress
    exec(
        compile(ast.fix_missing_locations(ast.Module([function], [])), str(source), "exec"),
        namespace,
    )
    progress("before_original_micro")
    namespace["micro"](root, root, output / "diagnostic-result.json")
    progress("after_original_micro")


if __name__ == "__main__":
    main()
