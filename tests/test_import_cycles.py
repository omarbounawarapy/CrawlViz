"""Backend packages import each other one way only (ARCH-5)."""

import ast
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src"
SRC_PACKAGE = "crawlviz"
NOT_BACKEND = {"tests", "tools", "docs", "crawler-ui"}


def _package_folders() -> dict[str, Path]:
    """Every backend package, keyed as it is imported.

    Top-level folders keep their own name (`config`); a domain under `src/crawlviz/` is
    keyed `crawlviz.<domain>`, so a cycle that runs through a moved domain is still seen.
    """
    folders = {
        path.parent.name: path.parent
        for path in REPO_ROOT.glob("*/__init__.py")
        if path.parent.name not in NOT_BACKEND and not path.parent.name.startswith(".")
    }
    for domain in sorted((SRC_ROOT / SRC_PACKAGE).iterdir()):
        if domain.is_dir() and any(domain.rglob("*.py")):
            folders[f"{SRC_PACKAGE}.{domain.name}"] = domain
    return folders


def _imported_packages(tree: ast.AST) -> set[str]:
    """Absolute imports at any depth, so a lazy import cannot hide a cycle.

    `from crawlviz.offline.x import y` counts as `crawlviz.offline`; any other import
    counts as its first dotted name.
    """

    def package_of(dotted: str) -> str:
        parts = dotted.split(".")
        return ".".join(parts[:2]) if parts[0] == SRC_PACKAGE else parts[0]

    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            if node.module == SRC_PACKAGE:
                names.update(f"{SRC_PACKAGE}.{alias.name}" for alias in node.names)
            else:
                names.add(package_of(node.module))
        elif isinstance(node, ast.Import):
            names.update(package_of(alias.name) for alias in node.names)
    return names


def _package_graph() -> dict[str, set[str]]:
    folders = _package_folders()
    graph: dict[str, set[str]] = defaultdict(set)
    for package, folder in folders.items():
        for source in folder.rglob("*.py"):
            tree = ast.parse(source.read_text(encoding="utf-8"))
            graph[package] |= (_imported_packages(tree) & folders.keys()) - {package}
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


def test_a_moved_domain_is_part_of_the_graph() -> None:
    assert f"{SRC_PACKAGE}.offline" in _package_folders()
    tree = ast.parse("from crawlviz.offline.session import x\nimport crawlviz.contracts.y")
    assert _imported_packages(tree) == {"crawlviz.offline", "crawlviz.contracts"}
