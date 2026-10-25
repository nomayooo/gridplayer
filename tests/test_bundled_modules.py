"""What the app imports as it loads, the Windows and macOS builds have:
none of the modules their PyInstaller specs leave out is imported at the
top of a module, which would stop the built app from starting at all
("No module named 'PyQt5.QtNetwork'"), while it runs from source.

A module for one platform alone (``*_linux.py``) is left to that one, and
an import inside a function is made only when it is reached.
"""

import ast
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SPECS = sorted((REPO / "scripts" / "pyinstaller").glob("*.spec"))
PLATFORM_ONLY = re.compile(r"_(linux|macos|mac|windows|win)\.py$")


def _excluded(spec: Path) -> set[str]:
    text = spec.read_text(encoding="utf-8")
    block = re.search(r"^excludes = \[(.*?)^\]", text, re.MULTILINE | re.DOTALL)
    assert block is not None, f"no excludes list in {spec.name}"
    return set(re.findall(r'"([\w.]+)"', block.group(1)))


def _top_level_imports(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []

    for node in tree.body:
        if isinstance(node, ast.Import):
            found.extend((node.lineno, alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            found.append((node.lineno, node.module))

    return found


def _is_excluded(module: str, excluded: set[str]) -> bool:
    return any(module == e or module.startswith(f"{e}.") for e in excluded)


@pytest.mark.parametrize("spec", SPECS, ids=lambda spec: spec.stem)
def test_no_module_left_out_of_a_build_is_imported_as_the_app_loads(spec):
    excluded = _excluded(spec)

    offending = [
        f"{path.relative_to(REPO)}:{line} imports {module}"
        for path in sorted((REPO / "gridplayer").rglob("*.py"))
        if not PLATFORM_ONLY.search(path.name)
        for line, module in _top_level_imports(path)
        if _is_excluded(module, excluded)
    ]

    assert offending == []


def test_the_specs_are_found():
    assert {spec.stem for spec in SPECS} >= {"pyinstaller_win", "pyinstaller_mac"}


def _all_imports(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend((node.lineno, alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            found.append((node.lineno, node.module))

    return found


def test_every_module_of_the_app_imported_anywhere_is_there():
    """Those imported only on one platform too, in a function or a branch
    the platform the tests run on never reaches."""

    package = REPO / "gridplayer"

    def exists(module: str) -> bool:
        parts = module.split(".")
        path = REPO.joinpath(*parts)
        return path.with_suffix(".py").is_file() or (path / "__init__.py").is_file()

    missing = [
        f"{path.relative_to(REPO)}:{line} imports {module}"
        for path in sorted(package.rglob("*.py"))
        for line, module in _all_imports(path)
        if module.split(".")[0] == "gridplayer" and not exists(module)
    ]

    assert missing == []
