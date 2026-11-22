"""NLPService refuses to work without a semantic space or a target vector, and says which call."""

import asyncio
from collections.abc import Coroutine
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from crawlviz.shared import Link
from services.nlp_service import NLPService
from tests.test_nlp_service import make

NEEDS_SPACE_MESSAGE = r"{caller}\(\) needs a semantic space; call NLPService\.start\(\) first"


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


def make_link() -> Link:
    return Link("http://s/a", "insulin in diabetes", "how diabetes treatment targets insulin")


def make_parent() -> SimpleNamespace:
    return SimpleNamespace(content="<p>diabetes and insulin treatment</p>")


def test_score_links_before_start_names_the_call(tmp_path: Path) -> None:
    svc = make(tmp_path)
    with pytest.raises(RuntimeError, match=NEEDS_SPACE_MESSAGE.format(caller="score_links")):
        run(svc.score_links([make_link()], make_parent()))


def test_flush_buffer_before_start_names_the_call(tmp_path: Path) -> None:
    svc = make(tmp_path)
    link = make_link()
    link.expansions = ["glucose metabolism"]
    # Expansions buffer locally without a space; flushing them is what needs one.
    run(svc.update_space([link]))
    with pytest.raises(RuntimeError, match=NEEDS_SPACE_MESSAGE.format(caller="flush_buffer")):
        svc.flush_buffer()


def test_flush_buffer_with_nothing_buffered_needs_no_space(tmp_path: Path) -> None:
    make(tmp_path).flush_buffer()


def test_start_names_itself_when_building_adopts_no_space(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    svc = make(tmp_path)

    async def build_nothing(self: NLPService) -> None:
        return None

    # start() asks for the space right after building; a build that adopts none must fail loudly.
    monkeypatch.setattr(NLPService, "build_space", build_nothing)
    with pytest.raises(RuntimeError, match=NEEDS_SPACE_MESSAGE.format(caller="start")):
        run(svc.start())


def test_score_links_with_space_but_no_target_vector_fails(tmp_path: Path) -> None:
    svc = make(tmp_path)

    async def go() -> None:
        await svc.start()
        svc.target_vec = None
        await svc.score_links([make_link()], make_parent())

    with pytest.raises(
        RuntimeError,
        match=r"score_links\(\) needs a target vector; call NLPService\.start\(\) first",
    ):
        run(go())


def test_start_then_score_does_not_trip_the_guards(tmp_path: Path) -> None:
    svc = make(tmp_path)

    async def go() -> list[Link]:
        await svc.start()
        return await svc.score_links([make_link()], make_parent())

    (scored,) = run(go())
    assert scored.nlp_vector
    assert scored._nlp_score > 0.0
