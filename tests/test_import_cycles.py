"""Backend packages import each other one way only (ARCH-5)."""

import ast
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
NOT_BACKEND = {"tests", "tools", "docs", "crawler-ui"}


def _backend_packages() -> set[str]:
    return {
        path.parent.name
        for path in REPO_ROOT.glob("*/__init__.py")
        if path.parent.name not in NOT_BACKEND and not path.parent.name.startswith(".")
    }


def _imported_top_levels(tree: ast.AST) -> set[str]:
    """Absolute imports at any depth, so a lazy import cannot hide a cycle."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
        elif isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
    return names


def _package_graph() -> dict[str, set[str]]:
    packages = _backend_packages()
    graph: dict[str, set[str]] = defaultdict(set)
    for package in packages:
        for source in (REPO_ROOT / package).rglob("*.py"):
            tree = ast.parse(source.read_text(encoding="utf-8"))
            graph[package] |= (_imported_top_levels(tree) & packages) - {package}
    return graph


def _find_cycle(graph: dict[str, set[str]]) -> list[str] | None:
    finished: set[str] = set()

    def visit(node: str, path: list[str]) -> list[str] | None:
        if node in path:
            return [*path[path.index(node) :], node]
        if node in finished:
            return None
        for neighbour in sorted(graph.get(node, ())):
            cycle = visit(neighbour, [*path, node])
            if cycle:
                return cycle
        finished.add(node)
        return None

    for start in sorted(graph):
        cycle = visit(start, [])
        if cycle:
            return cycle
    return None


def test_backend_packages_have_no_import_cycle() -> None:
    cycle = _find_cycle(_package_graph())
    assert cycle is None, "import cycle: " + " -> ".join(cycle or [])


def test_cycle_finder_reports_a_cycle() -> None:
    assert _find_cycle({"a": {"b"}, "b": {"c"}, "c": {"a"}}) == ["a", "b", "c", "a"]
    assert _find_cycle({"a": {"b"}, "b": {"c"}}) is None
