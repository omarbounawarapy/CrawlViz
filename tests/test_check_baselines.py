"""Rules of the shrink-only baseline guard (tools/check_baselines.py)."""

import subprocess
from pathlib import Path

import pytest

from tools import check_baselines as guard
from tools.check_baselines import Baselines

CRAWLER_BODY = "\n".join(f"line {number}" for number in range(30))


def baselines(
    mypy_modules: set[str] | None = None, ruff_codes: dict[str, set[str]] | None = None
) -> Baselines:
    return Baselines(
        frozenset(mypy_modules or set()),
        {path: frozenset(codes) for path, codes in (ruff_codes or {}).items()},
    )


PYPROJECT_WITH_BASELINES = """
[tool.mypy]
strict = true

[[tool.mypy.overrides]]
module = ["aiofiles.*"]
ignore_missing_imports = true

[[tool.mypy.overrides]]
module = ["core.crawler", "models.node"]
ignore_errors = true

[[tool.mypy.overrides]]
module = ["routes.run"]
ignore_errors = false

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["PLR2004"]
"main.py" = ["I001", "E501"]
"""


class TestParseBaselines:
    def test_collects_modules_whose_override_sets_ignore_errors_true(self) -> None:
        parsed = guard.parse_baselines(PYPROJECT_WITH_BASELINES)

        assert parsed.mypy_modules == {"core.crawler", "models.node"}

    def test_ignores_overrides_without_ignore_errors_true(self) -> None:
        parsed = guard.parse_baselines(PYPROJECT_WITH_BASELINES)

        assert "aiofiles.*" not in parsed.mypy_modules
        assert "routes.run" not in parsed.mypy_modules

    def test_collects_ruff_codes_per_file_and_glob(self) -> None:
        parsed = guard.parse_baselines(PYPROJECT_WITH_BASELINES)

        assert parsed.ruff_codes == {
            "tests/**": frozenset({"PLR2004"}),
            "main.py": frozenset({"I001", "E501"}),
        }

    def test_a_single_module_given_as_a_string_is_one_module_not_characters(self) -> None:
        parsed = guard.parse_baselines(
            '[[tool.mypy.overrides]]\nmodule = "core.crawler"\nignore_errors = true\n'
        )

        assert parsed.mypy_modules == {"core.crawler"}

    def test_file_without_tool_tables_has_no_baselines(self) -> None:
        parsed = guard.parse_baselines('[project]\nname = "demo"\n')

        assert parsed == baselines()


class TestPathHelpers:
    @pytest.mark.parametrize(
        ("path", "module"),
        [
            ("core/crawler.py", "core.crawler"),
            ("core/__init__.py", "core"),
            ("main.py", "main"),
            ("src/crawlviz/fetch/__init__.py", "src.crawlviz.fetch"),
        ],
    )
    def test_path_to_module(self, path: str, module: str) -> None:
        assert guard.path_to_module(path) == module

    @pytest.mark.parametrize("key", ["tests/**", "*.py", "tests/test_?.py", "tests/[ab].py"])
    def test_glob_characters_make_a_glob(self, key: str) -> None:
        assert guard.is_glob(key)

    @pytest.mark.parametrize("key", ["main.py", "core/crawler.py"])
    def test_plain_path_is_not_a_glob(self, key: str) -> None:
        assert not guard.is_glob(key)


class TestFindAdditions:
    def test_identical_baselines_have_no_additions(self) -> None:
        both = baselines({"core.crawler"}, {"main.py": {"I001"}})

        assert guard.find_additions(both, both, {}) == []

    def test_shrinking_is_not_growth(self) -> None:
        base = baselines({"core.crawler", "models.node"}, {"main.py": {"I001", "E501"}})
        current = baselines({"core.crawler"}, {"main.py": {"I001"}})

        assert guard.find_additions(base, current, {}) == []

    def test_new_mypy_module_is_growth(self) -> None:
        base = baselines({"core.crawler"})
        current = baselines({"core.crawler", "routes.run"})

        assert guard.find_additions(base, current, {}) == ["mypy legacy list gained routes.run"]

    def test_new_ruff_code_for_existing_file_is_growth(self) -> None:
        base = baselines(ruff_codes={"main.py": {"I001"}})
        current = baselines(ruff_codes={"main.py": {"I001", "E501"}})

        assert guard.find_additions(base, current, {}) == ["ruff baseline gained E501 for main.py"]

    def test_new_file_entry_is_growth_for_every_code(self) -> None:
        base = baselines(ruff_codes={"main.py": {"I001"}})
        current = baselines(ruff_codes={"main.py": {"I001"}, "routes/run.py": {"B904", "E501"}})

        assert guard.find_additions(base, current, {}) == [
            "ruff baseline gained B904 for routes/run.py",
            "ruff baseline gained E501 for routes/run.py",
        ]

    def test_renamed_ruff_path_is_not_growth(self) -> None:
        base = baselines(ruff_codes={"core/crawler.py": {"I001"}})
        current = baselines(ruff_codes={"src/crawlviz/crawl/crawler.py": {"I001"}})
        renames = {"core/crawler.py": "src/crawlviz/crawl/crawler.py"}

        assert guard.find_additions(base, current, renames) == []

    def test_renamed_ruff_path_still_catches_a_new_code(self) -> None:
        base = baselines(ruff_codes={"core/crawler.py": {"I001"}})
        current = baselines(ruff_codes={"crawl/crawler.py": {"I001", "C901"}})

        assert guard.find_additions(base, current, {"core/crawler.py": "crawl/crawler.py"}) == [
            "ruff baseline gained C901 for crawl/crawler.py"
        ]

    def test_renamed_mypy_module_is_not_growth(self) -> None:
        base = baselines({"core.crawler"})
        current = baselines({"src.crawlviz.crawl.crawler"})
        renames = {"core/crawler.py": "src/crawlviz/crawl/crawler.py"}

        assert guard.find_additions(base, current, renames) == []

    def test_renamed_package_init_maps_to_the_package_module(self) -> None:
        base = baselines({"events"})
        current = baselines({"src.crawlviz.events"})
        renames = {"events/__init__.py": "src/crawlviz/events/__init__.py"}

        assert guard.find_additions(base, current, renames) == []

    def test_rename_of_an_unlisted_file_does_not_excuse_a_new_entry(self) -> None:
        base = baselines({"core.crawler"})
        current = baselines({"core.crawler", "crawl.pacer"})

        assert guard.find_additions(base, current, {"core/pacer.py": "crawl/pacer.py"}) == [
            "mypy legacy list gained crawl.pacer"
        ]


class TestFindStaleRuff:
    def test_code_that_still_violates_is_not_stale(self) -> None:
        current = baselines(ruff_codes={"main.py": {"I001"}})

        assert guard.find_stale_ruff(current, {("main.py", "I001")}, {"main.py"}) == []

    def test_code_without_a_violation_is_stale(self) -> None:
        current = baselines(ruff_codes={"main.py": {"I001", "E501"}})

        assert guard.find_stale_ruff(current, {("main.py", "I001")}, {"main.py"}) == [
            "ruff baseline lists E501 for main.py, which no longer violates it"
        ]

    def test_violation_in_another_file_does_not_keep_the_code_alive(self) -> None:
        current = baselines(ruff_codes={"main.py": {"I001"}})

        assert guard.find_stale_ruff(current, {("routes/run.py", "I001")}, {"main.py"}) == [
            "ruff baseline lists I001 for main.py, which no longer violates it"
        ]

    def test_entry_for_a_missing_file_is_reported_once(self) -> None:
        current = baselines(ruff_codes={"gone.py": {"I001", "E501"}})

        assert guard.find_stale_ruff(current, set(), set()) == [
            "ruff baseline lists gone.py, which does not exist"
        ]

    def test_glob_keys_are_never_stale(self) -> None:
        current = baselines(ruff_codes={"tests/**": {"PLR2004"}})

        assert guard.find_stale_ruff(current, set(), set()) == []


class TestFindStaleMypy:
    def test_module_with_errors_is_not_stale(self) -> None:
        current = baselines({"core.crawler"})

        assert guard.find_stale_mypy(current, {"core.crawler", "routes.run"}) == []

    def test_strict_clean_or_missing_module_is_stale(self) -> None:
        current = baselines({"core.crawler", "models.node"})

        assert guard.find_stale_mypy(current, {"core.crawler"}) == [
            "mypy legacy list names models.node, which is strict-clean or gone: remove it"
        ]


class TestParseMypyModules:
    def test_maps_error_lines_to_modules(self) -> None:
        output = (
            "core/crawler.py:12: error: Missing return statement  [return]\n"
            "models/node.py:7:5: error: Function is missing a type annotation  [no-untyped-def]\n"
            "Found 2 errors in 2 files (checked 40 source files)\n"
        )

        assert guard.parse_mypy_modules(output) == {"core.crawler", "models.node"}

    def test_maps_package_init_to_the_package(self) -> None:
        output = "events/__init__.py:3: error: Name 'x' is not defined  [name-defined]\n"

        assert guard.parse_mypy_modules(output) == {"events"}

    def test_ignores_notes_and_summary_lines(self) -> None:
        output = (
            "core/crawler.py:12: note: See https://mypy.readthedocs.io for more info\n"
            "Success: no issues found in 40 source files\n"
        )

        assert guard.parse_mypy_modules(output) == set()

    def test_counts_a_module_once_however_many_errors_it_has(self) -> None:
        output = "main.py:1: error: first  [misc]\nmain.py:2: error: second  [misc]\n"

        assert guard.parse_mypy_modules(output) == {"main"}


def git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
         "-c", "commit.gpgsign=false", "-c", "init.defaultBranch=main", *args],
        cwd=repo, check=True, capture_output=True, text=True,
    )


def commit_all(repo: Path, message: str) -> None:
    git(repo, "add", "-A")
    git(repo, "commit", "-m", message)


def write_pyproject(repo: Path, modules: list[str]) -> None:
    listed = ", ".join(f'"{module}"' for module in modules)
    (repo / "pyproject.toml").write_text(
        f"[[tool.mypy.overrides]]\nmodule = [{listed}]\nignore_errors = true\n"
    )


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A throwaway git repository that the guard treats as the project root."""
    git(tmp_path, "init")
    monkeypatch.setattr(guard, "ROOT", tmp_path)
    return tmp_path


class TestRenamesFromGit:
    def test_git_mv_is_read_as_a_rename(self, repo: Path) -> None:
        (repo / "core").mkdir()
        (repo / "core" / "crawler.py").write_text(CRAWLER_BODY)
        commit_all(repo, "Add crawler")
        (repo / "crawl").mkdir()
        git(repo, "mv", "core/crawler.py", "crawl/crawler.py")
        commit_all(repo, "Move crawler")

        assert guard.read_renames("HEAD~1") == {"core/crawler.py": "crawl/crawler.py"}

    def test_edit_without_a_move_is_not_a_rename(self, repo: Path) -> None:
        (repo / "main.py").write_text("print('a')\n")
        commit_all(repo, "Add main")
        (repo / "main.py").write_text("print('b')\n")
        commit_all(repo, "Edit main")

        assert guard.read_renames("HEAD~1") == {}


class TestMain:
    @staticmethod
    def run_main(monkeypatch: pytest.MonkeyPatch) -> int:
        monkeypatch.setattr("sys.argv", ["check_baselines", "--skip-stale"])
        return guard.main()

    def test_accepts_a_baseline_that_only_moved(
        self, repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        (repo / "core").mkdir()
        (repo / "core" / "crawler.py").write_text(CRAWLER_BODY)
        write_pyproject(repo, ["core.crawler"])
        commit_all(repo, "Baseline")
        git(repo, "checkout", "-b", "feature")
        (repo / "crawl").mkdir()
        git(repo, "mv", "core/crawler.py", "crawl/crawler.py")
        write_pyproject(repo, ["crawl.crawler"])
        commit_all(repo, "Move crawler")

        assert self.run_main(monkeypatch) == 0
        assert "did not grow" in capsys.readouterr().out

    def test_rejects_a_new_legacy_module(
        self, repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        write_pyproject(repo, ["core.crawler"])
        commit_all(repo, "Baseline")
        git(repo, "checkout", "-b", "feature")
        write_pyproject(repo, ["core.crawler", "routes.run"])
        commit_all(repo, "Grow baseline")

        assert self.run_main(monkeypatch) == 1
        output = capsys.readouterr().out
        assert "mypy legacy list gained routes.run" in output
        assert "baselines may only shrink" in output

    def test_skips_the_growth_check_when_the_base_has_no_baselines(
        self, repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        (repo / "pyproject.toml").write_text('[project]\nname = "demo"\n')
        commit_all(repo, "No baselines yet")
        git(repo, "checkout", "-b", "feature")
        write_pyproject(repo, ["core.crawler"])
        commit_all(repo, "Introduce baselines")

        assert self.run_main(monkeypatch) == 0
        assert "has no baselines yet" in capsys.readouterr().out
