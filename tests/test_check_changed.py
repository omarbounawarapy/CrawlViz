"""Selection rules of the changed-file checker (tools/check_changed.py).

The tool reads the repository through git, so these tests build a small repository under
``tmp_path`` and point the tool's ``ROOT`` at it. Nothing here touches the real checkout.
"""

import ast
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from tools import check_changed as tool

OWNERSHIP_FILE = Path(__file__).resolve().parent.parent / ".claude" / "ownership.toml"
SYNTAX_ERROR_SOURCE = "def broken(:\n"
GIT_IDENTITY = (
    "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
    "-c", "commit.gpgsign=false", "-c", "init.defaultBranch=main",
)


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *GIT_IDENTITY, *args], cwd=repo, check=True, capture_output=True)


def write(repo: Path, relative: str, text: str = "") -> Path:
    path = repo / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def names(repo: Path, paths: list[Path]) -> list[str]:
    return [path.relative_to(repo).as_posix() for path in paths]


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A throwaway git repository that the tool treats as the project root."""
    git(tmp_path, "init")
    monkeypatch.setattr(tool, "ROOT", tmp_path)
    monkeypatch.setattr(tool, "UI_DIR", tmp_path / "crawler-ui")
    return tmp_path


def selected_tests(repo: Path, *changed: str) -> list[str]:
    return names(repo, tool.python_tests_for([repo / name for name in changed]))


class TestImportCandidates:
    @staticmethod
    def candidates(source: str, directory: tuple[str, ...]) -> set[str]:
        return tool._import_candidates(ast.parse(source).body[0], directory)

    def test_plain_import_names_the_module_and_its_sibling_form(self) -> None:
        assert self.candidates("import pkg.mod", ("tests",)) == {"pkg.mod", "tests.pkg.mod"}

    def test_from_import_includes_each_imported_name_as_a_submodule(self) -> None:
        assert self.candidates("from pkg import mod, other", ()) == {
            "pkg", "pkg.mod", "pkg.other", ".pkg", ".pkg.mod", ".pkg.other",
        }

    def test_relative_import_resolves_against_the_importing_directory(self) -> None:
        assert self.candidates("from .low import f", ("pkg",)) == {"pkg.low", "pkg.low.f"}

    def test_bare_relative_import_names_the_package_and_each_submodule(self) -> None:
        assert self.candidates("from . import low", ("pkg",)) == {"pkg", "pkg.low"}

    def test_two_dots_climb_one_directory(self) -> None:
        assert self.candidates("from ..util import f", ("pkg", "sub")) == {"pkg.util", "pkg.util.f"}

    def test_statement_that_is_not_an_import_has_no_candidates(self) -> None:
        assert self.candidates("value = 1", ("pkg",)) == set()


class TestImportsOf:
    def test_collects_repo_files_and_ignores_the_standard_library(self, repo: Path) -> None:
        write(repo, "pkg/__init__.py")
        mod = write(repo, "pkg/mod.py")
        user = write(repo, "pkg/user.py", "import os\nfrom pkg import mod\n")
        modules = tool.python_modules()

        assert tool.imports_of(user, modules) == {mod, repo / "pkg/__init__.py"}

    def test_a_file_does_not_import_itself(self, repo: Path) -> None:
        loop = write(repo, "pkg/loop.py", "import pkg.loop\n")

        assert tool.imports_of(loop, tool.python_modules()) == set()

    def test_syntax_error_yields_no_imports(self, repo: Path) -> None:
        write(repo, "pkg/mod.py")
        broken = write(repo, "pkg/broken.py", SYNTAX_ERROR_SOURCE)

        assert tool.imports_of(broken, tool.python_modules()) == set()

    def test_undecodable_file_yields_no_imports(self, repo: Path) -> None:
        write(repo, "pkg/mod.py")
        binary = repo / "pkg" / "binary.py"
        binary.write_bytes(b"\xff\xfe\x00import pkg.mod\n")

        assert tool.imports_of(binary, tool.python_modules()) == set()


class TestPythonModules:
    def test_names_packages_by_their_init_file(self, repo: Path) -> None:
        init = write(repo, "pkg/__init__.py")
        mod = write(repo, "pkg/mod.py")
        top = write(repo, "main.py")

        assert tool.python_modules() == {"pkg": init, "pkg.mod": mod, "main": top}

    def test_ignores_files_git_ignores_and_non_python_files(self, repo: Path) -> None:
        write(repo, ".gitignore", "build/\n")
        write(repo, "build/generated.py")
        write(repo, "notes.txt")
        kept = write(repo, "main.py")

        assert tool.python_modules() == {"main": kept}


class TestPythonTestsFor:
    def test_selects_a_test_that_imports_the_changed_module_directly(self, repo: Path) -> None:
        write(repo, "pkg/__init__.py")
        write(repo, "pkg/mod.py")
        write(repo, "tests/test_mod.py", "import pkg.mod\n")
        write(repo, "tests/test_unrelated.py", "import os\n")

        assert selected_tests(repo, "pkg/mod.py") == ["tests/test_mod.py"]

    def test_selects_a_test_that_uses_from_import_of_the_module(self, repo: Path) -> None:
        write(repo, "pkg/__init__.py")
        write(repo, "pkg/mod.py")
        write(repo, "tests/test_mod.py", "from pkg import mod\n")

        assert selected_tests(repo, "pkg/mod.py") == ["tests/test_mod.py"]

    def test_selects_a_test_that_reaches_the_change_through_another_module(
        self, repo: Path
    ) -> None:
        write(repo, "pkg/__init__.py")
        write(repo, "pkg/low.py")
        write(repo, "pkg/mid.py", "from pkg import low\n")
        write(repo, "pkg/high.py", "import pkg.mid\n")
        write(repo, "tests/test_high.py", "import pkg.high\n")

        assert selected_tests(repo, "pkg/low.py") == ["tests/test_high.py"]

    def test_follows_relative_imports_between_source_modules(self, repo: Path) -> None:
        write(repo, "pkg/__init__.py")
        write(repo, "pkg/low.py")
        write(repo, "pkg/high.py", "from .low import helper\n")
        write(repo, "tests/test_high.py", "import pkg.high\n")

        assert selected_tests(repo, "pkg/low.py") == ["tests/test_high.py"]

    def test_follows_a_relative_import_inside_the_tests_package(self, repo: Path) -> None:
        write(repo, "tests/__init__.py")
        write(repo, "tests/support.py")
        write(repo, "tests/test_uses_support.py", "from .support import helper\n")
        write(repo, "tests/test_other.py")

        assert selected_tests(repo, "tests/support.py") == ["tests/test_uses_support.py"]

    def test_follows_a_bare_sibling_import_like_tests_pins(self, repo: Path) -> None:
        write(repo, "tests/pins/pin_helpers.py")
        write(repo, "tests/pins/test_pin_one.py", "import pin_helpers\n")
        write(repo, "tests/pins/test_pin_two.py", "from pin_helpers import build\n")
        write(repo, "tests/test_elsewhere.py")

        assert selected_tests(repo, "tests/pins/pin_helpers.py") == [
            "tests/pins/test_pin_one.py",
            "tests/pins/test_pin_two.py",
        ]

    def test_bare_name_in_another_directory_is_not_a_sibling(self, repo: Path) -> None:
        write(repo, "tests/pins/pin_helpers.py")
        write(repo, "tests/other/test_other.py", "import pin_helpers\n")

        assert selected_tests(repo, "tests/pins/pin_helpers.py") == []

    def test_changed_package_init_selects_tests_importing_a_deeper_module(
        self, repo: Path
    ) -> None:
        write(repo, "a/__init__.py")
        write(repo, "a/b/__init__.py")
        write(repo, "a/b/c.py")
        write(repo, "tests/test_deep.py", "import a.b.c\n")
        write(repo, "tests/test_other.py", "import os\n")

        assert selected_tests(repo, "a/__init__.py") == ["tests/test_deep.py"]
        assert selected_tests(repo, "a/b/__init__.py") == ["tests/test_deep.py"]

    def test_a_deleted_module_selects_tests_that_still_import_it(self, repo: Path) -> None:
        write(repo, "utils/__init__.py")
        write(repo, "utils/foo.py")
        write(repo, "tests/test_foo.py", "from utils.foo import thing\n")
        write(repo, "tests/test_bar.py", "import utils\n")
        write(repo, "tests/test_other.py")
        git(repo, "add", "-A")
        git(repo, "commit", "-m", "Base")
        git(repo, "rm", "utils/foo.py")

        assert selected_tests(repo, "utils/foo.py") == ["tests/test_foo.py"]

    def test_a_deleted_package_init_selects_tests_that_import_the_package(
        self, repo: Path
    ) -> None:
        write(repo, "pkg/__init__.py")
        write(repo, "tests/test_pkg.py", "import pkg.sub\n")
        git(repo, "add", "-A")
        git(repo, "commit", "-m", "Base")
        git(repo, "rm", "pkg/__init__.py")

        assert selected_tests(repo, "pkg/__init__.py") == ["tests/test_pkg.py"]

    def test_changed_conftest_selects_every_test_beneath_its_directory(self, repo: Path) -> None:
        write(repo, "tests/pins/conftest.py")
        write(repo, "tests/pins/test_a.py")
        write(repo, "tests/pins/nested/test_b.py")
        write(repo, "tests/test_outside.py")

        assert selected_tests(repo, "tests/pins/conftest.py") == [
            "tests/pins/nested/test_b.py",
            "tests/pins/test_a.py",
        ]

    def test_changed_top_level_conftest_selects_the_whole_suite(self, repo: Path) -> None:
        write(repo, "tests/conftest.py")
        write(repo, "tests/test_a.py")
        write(repo, "tests/pins/test_b.py")

        assert selected_tests(repo, "tests/conftest.py") == [
            "tests/pins/test_b.py",
            "tests/test_a.py",
        ]

    def test_changed_test_file_selects_itself(self, repo: Path) -> None:
        write(repo, "tests/test_a.py")
        write(repo, "tests/test_b.py")

        assert selected_tests(repo, "tests/test_a.py") == ["tests/test_a.py"]

    def test_file_with_a_syntax_error_is_skipped_not_fatal(self, repo: Path) -> None:
        write(repo, "pkg/__init__.py")
        write(repo, "pkg/mod.py")
        write(repo, "tests/test_broken.py", SYNTAX_ERROR_SOURCE)
        write(repo, "tests/test_mod.py", "import pkg.mod\n")

        assert selected_tests(repo, "pkg/mod.py") == ["tests/test_mod.py"]

    def test_change_nobody_imports_selects_nothing(self, repo: Path) -> None:
        write(repo, "pkg/lonely.py")
        write(repo, "tests/test_a.py", "import os\n")

        assert selected_tests(repo, "pkg/lonely.py") == []

    def test_import_cycle_terminates(self, repo: Path) -> None:
        write(repo, "pkg/__init__.py")
        write(repo, "pkg/one.py", "import pkg.two\n")
        write(repo, "pkg/two.py", "import pkg.one\n")
        write(repo, "tests/test_cycle.py", "import pkg.one\n")

        assert selected_tests(repo, "pkg/two.py") == ["tests/test_cycle.py"]

    def test_only_test_files_under_a_tests_directory_are_selected(self, repo: Path) -> None:
        write(repo, "pkg/__init__.py")
        write(repo, "pkg/mod.py")
        write(repo, "pkg/test_inside_source.py", "import pkg.mod\n")
        write(repo, "tests/helpers.py", "import pkg.mod\n")

        assert selected_tests(repo, "pkg/mod.py") == []


class TestChangedFiles:
    def commit_all(self, repo: Path, message: str) -> None:
        git(repo, "add", "-A")
        git(repo, "commit", "-m", message)

    def test_reports_committed_staged_unstaged_and_untracked_changes(self, repo: Path) -> None:
        write(repo, "kept.py", "x = 1\n")
        write(repo, "edited.py", "x = 1\n")
        self.commit_all(repo, "Base")
        git(repo, "checkout", "-b", "feature")
        write(repo, "committed.py")
        self.commit_all(repo, "Add committed file")
        write(repo, "staged.py")
        git(repo, "add", "staged.py")
        write(repo, "edited.py", "x = 2\n")
        write(repo, "untracked.py")

        assert names(repo, tool.changed_files("main")) == [
            "committed.py", "edited.py", "staged.py", "untracked.py",
        ]

    def test_a_deleted_file_is_reported(self, repo: Path) -> None:
        write(repo, "gone.py")
        self.commit_all(repo, "Base")
        git(repo, "checkout", "-b", "feature")
        git(repo, "rm", "gone.py")
        self.commit_all(repo, "Delete file")

        assert names(repo, tool.changed_files("main")) == ["gone.py"]

    def test_git_mv_reports_the_old_and_the_new_path(self, repo: Path) -> None:
        write(repo, "old/crawler.py", "\n".join(f"line {number}" for number in range(30)))
        self.commit_all(repo, "Base")
        git(repo, "checkout", "-b", "feature")
        (repo / "new").mkdir()
        git(repo, "mv", "old/crawler.py", "new/crawler.py")
        self.commit_all(repo, "Move crawler")

        assert names(repo, tool.changed_files("main")) == ["new/crawler.py", "old/crawler.py"]

    def test_unknown_base_stops_instead_of_skipping_committed_changes(self, repo: Path) -> None:
        write(repo, "base.py")
        self.commit_all(repo, "Base")
        write(repo, "fresh.py")

        with pytest.raises(SystemExit, match="no-such-branch"):
            tool.changed_files("no-such-branch")


class TestTouchesMethod:
    def paths(self, repo: Path, *relative: str) -> list[Path]:
        return [repo / name for name in relative]

    @pytest.mark.parametrize(
        "relative",
        [
            "priority/queue_strategy.py",
            "nlp/embedding_engine.py",
            "models/prompts.py",
            "core/crawler.py",
            "core/event_broker.py",
        ],
    )
    def test_method_files_are_detected(self, repo: Path, relative: str) -> None:
        assert tool.touches_method(self.paths(repo, relative))

    def test_every_literal_entry_of_the_ownership_method_list_is_detected(
        self, repo: Path
    ) -> None:
        with OWNERSHIP_FILE.open("rb") as handle:
            patterns: list[str] = tomllib.load(handle)["shared"]["method_files"]
        literal = [pattern for pattern in patterns if "*" not in pattern]

        assert literal
        for relative in literal:
            assert tool.touches_method(self.paths(repo, relative)), relative

    @pytest.mark.parametrize(
        "relative", ["routes/run.py", "tests/test_nlp_service.py", "README.md"]
    )
    def test_other_files_are_not_method_files(self, repo: Path, relative: str) -> None:
        assert not tool.touches_method(self.paths(repo, relative))

    def test_one_method_file_among_others_is_enough(self, repo: Path) -> None:
        assert tool.touches_method(self.paths(repo, "routes/run.py", "priority/queue.py"))

    def test_no_files_do_not_touch_the_method(self, repo: Path) -> None:
        assert not tool.touches_method([])


class RecordedRuns:
    """Stands in for `tool.run` so no linter or test process starts."""

    def __init__(self, results: dict[str, bool] | None = None) -> None:
        self.commands: list[tuple[list[str], Path, tuple[int, ...]]] = []
        self.results = results or {}

    def __call__(
        self, command: list[str], cwd: Path, accepted: tuple[int, ...] = (0,)
    ) -> bool:
        self.commands.append((command, cwd, accepted))
        return self.results.get(command[2], True)

    def tools_run(self) -> list[str]:
        return [command[2] for command, _cwd, _accepted in self.commands]

    def command_for(self, tool_name: str) -> list[str]:
        return next(command for command, _cwd, _accepted in self.commands
                    if command[2] == tool_name)


@pytest.fixture
def runs(monkeypatch: pytest.MonkeyPatch) -> RecordedRuns:
    recorded = RecordedRuns()
    monkeypatch.setattr(tool, "run", recorded)
    return recorded


class TestRun:
    def test_zero_exit_is_success_and_other_exits_fail(self) -> None:
        assert tool.run([sys.executable, "-c", "pass"], Path.cwd())
        assert not tool.run([sys.executable, "-c", "raise SystemExit(1)"], Path.cwd())

    def test_accepted_exit_codes_count_as_success(self) -> None:
        command = [sys.executable, "-c", "raise SystemExit(5)"]

        assert not tool.run(command, Path.cwd())
        assert tool.run(command, Path.cwd(), accepted=(0, tool.PYTEST_NO_TESTS_COLLECTED))


class TestCheckPython:
    def test_lints_changed_files_and_runs_only_their_tests(
        self, repo: Path, runs: RecordedRuns
    ) -> None:
        write(repo, "pkg/__init__.py")
        mod = write(repo, "pkg/mod.py")
        write(repo, "tests/test_mod.py", "import pkg.mod\n")
        write(repo, "tests/test_unrelated.py")

        assert tool.check_python([mod], tooling_changed=False)

        assert runs.command_for("ruff") == ["uv", "run", "ruff", "check", "pkg/mod.py"]
        assert runs.command_for("mypy") == ["uv", "run", "mypy"]
        assert runs.command_for("pytest") == [
            "uv", "run", "pytest", "-q", "-m", "not slow", "tests/test_mod.py",
        ]

    def test_pytest_exit_code_for_no_collected_tests_is_accepted(
        self, repo: Path, runs: RecordedRuns
    ) -> None:
        write(repo, "tests/test_a.py")

        tool.check_python([repo / "tests/test_a.py"], tooling_changed=False)

        *_, (_command, _cwd, accepted) = runs.commands
        assert tool.PYTEST_NO_TESTS_COLLECTED in accepted

    def test_changed_tooling_checks_everything(self, repo: Path, runs: RecordedRuns) -> None:
        write(repo, "tests/test_a.py")
        pyproject = write(repo, "pyproject.toml")

        assert tool.check_python([pyproject], tooling_changed=True)

        assert runs.command_for("ruff") == ["uv", "run", "ruff", "check"]
        assert runs.command_for("pytest") == ["uv", "run", "pytest", "-q", "-m", "not slow"]

    def test_change_without_covering_tests_skips_pytest(
        self, repo: Path, runs: RecordedRuns
    ) -> None:
        lonely = write(repo, "pkg/lonely.py")

        assert tool.check_python([lonely], tooling_changed=False)

        assert runs.tools_run() == ["ruff", "mypy"]

    def test_a_failing_linter_fails_the_check_but_the_rest_still_run(
        self, repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        failing = RecordedRuns({"ruff": False})
        monkeypatch.setattr(tool, "run", failing)
        lonely = write(repo, "pkg/lonely.py")

        assert not tool.check_python([lonely], tooling_changed=False)
        assert failing.tools_run() == ["ruff", "mypy"]


class TestMain:
    @staticmethod
    def run_main(monkeypatch: pytest.MonkeyPatch) -> int:
        monkeypatch.setattr("sys.argv", ["check_changed"])
        return tool.main()

    def test_a_deletion_only_change_still_runs_mypy_and_the_tests_that_imported_it(
        self, repo: Path, runs: RecordedRuns, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        write(repo, "utils/foo.py")
        write(repo, "tests/test_foo.py", "import utils.foo\n")
        git(repo, "add", "-A")
        git(repo, "commit", "-m", "Base")
        git(repo, "rm", "utils/foo.py")

        assert self.run_main(monkeypatch) == 0

        assert runs.tools_run() == ["mypy", "pytest"]
        assert runs.command_for("pytest")[-1] == "tests/test_foo.py"

    def test_no_changes_run_nothing(
        self, repo: Path, runs: RecordedRuns, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        write(repo, "README.md")
        git(repo, "add", "-A")
        git(repo, "commit", "-m", "Base")

        assert self.run_main(monkeypatch) == 0
        assert runs.commands == []
        assert "no Python or UI source changes" in capsys.readouterr().out

    def test_method_file_change_also_runs_pins_and_method_guards_unfiltered(
        self, repo: Path, runs: RecordedRuns, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        git(repo, "commit", "--allow-empty", "-m", "Base")
        write(repo, "priority/queue.py")

        assert self.run_main(monkeypatch) == 0

        pytest_commands = [command for command, _cwd, _accepted in runs.commands
                           if command[2] == "pytest"]
        assert ["uv", "run", "pytest", "-q", "-m", "pins or method_guard"] in pytest_commands
        assert all("not slow" not in command for command in pytest_commands
                   if "pins or method_guard" in command)

    def test_ordinary_change_does_not_run_the_pins(
        self, repo: Path, runs: RecordedRuns, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        git(repo, "commit", "--allow-empty", "-m", "Base")
        write(repo, "routes/run.py")

        assert self.run_main(monkeypatch) == 0
        assert ["uv", "run", "pytest", "-q", "-m", "pins or method_guard"] not in [
            command for command, _cwd, _accepted in runs.commands
        ]

    def test_changed_ui_file_runs_eslint_and_vitest_from_the_ui_directory(
        self, repo: Path, runs: RecordedRuns, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        git(repo, "commit", "--allow-empty", "-m", "Base")
        write(repo, "crawler-ui/src/App.tsx")
        write(repo, "crawler-ui/node_modules/dep/index.js")

        assert self.run_main(monkeypatch) == 0

        ui_runs = [(command, cwd) for command, cwd, _accepted in runs.commands
                   if cwd == repo / "crawler-ui"]
        assert [command[1] for command, _cwd in ui_runs] == ["eslint", "vitest"]
        assert all("src/App.tsx" in command for command, _cwd in ui_runs)
        assert all(not any("node_modules" in part for part in command)
                   for command, _cwd in ui_runs)

    def test_exit_code_is_one_when_any_check_fails(
        self, repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(tool, "run", RecordedRuns({"mypy": False}))
        git(repo, "commit", "--allow-empty", "-m", "Base")
        write(repo, "pkg/lonely.py")

        assert self.run_main(monkeypatch) == 1

    def test_changed_pyproject_selects_the_whole_python_side(
        self, repo: Path, runs: RecordedRuns, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        git(repo, "commit", "--allow-empty", "-m", "Base")
        write(repo, "pyproject.toml")

        assert self.run_main(monkeypatch) == 0
        assert runs.command_for("ruff") == ["uv", "run", "ruff", "check"]
        assert runs.command_for("pytest") == ["uv", "run", "pytest", "-q", "-m", "not slow"]
