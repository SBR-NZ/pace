"""The tools and their checks say Python 3.8 or later, so none of them may need a newer Python to load.

This reads the source rather than running an old Python, which may not be installed.
"""

import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
FILES = sorted([*ROOT.glob("tests/*.py"), *(ROOT / "PACE/Product/Tools").glob("*.py"), ROOT / "get-pace.py"])
NEWER_GENERICS = {"dict", "frozenset", "list", "set", "tuple", "type"}


def loaded_annotations(tree):
    """Annotations Python evaluates when the file loads (without the annotations future import)."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            given = node.args
            for arg in given.posonlyargs + given.args + given.kwonlyargs + [given.vararg, given.kwarg]:
                if arg is not None and arg.annotation is not None:
                    yield arg.annotation
            if node.returns is not None:
                yield node.returns
        elif isinstance(node, ast.AnnAssign):
            yield node.annotation


def newer_forms(annotation):
    for node in ast.walk(annotation):
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            yield "X | Y needs Python 3.10"
        elif isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) and node.value.id in NEWER_GENERICS:
            yield f"{node.value.id}[...] needs Python 3.9"


class PythonSupportTests(unittest.TestCase):
    def test_every_tool_and_check_loads_on_python_3_8(self):
        # tests/test_release_note.py used "dict | None" without the future import, so it failed to load on 3.9.
        self.assertIn(ROOT / "tests/test_release_note.py", FILES)
        for path in FILES:
            with self.subTest(file=path.relative_to(ROOT).as_posix()):
                source = path.read_text(encoding="utf-8")
                tree = ast.parse(source, filename=str(path), feature_version=(3, 8))
                postponed = any(isinstance(node, ast.ImportFrom) and node.module == "__future__"
                                and any(alias.name == "annotations" for alias in node.names) for node in tree.body)
                if postponed:
                    continue
                problems = [f"line {annotation.lineno}: {form}"
                            for annotation in loaded_annotations(tree) for form in newer_forms(annotation)]
                self.assertEqual(problems, [])


if __name__ == "__main__":
    unittest.main()
