"""A benchmark job's log goes to the UI and to last_job.json, so a subprocess that prints a
failed request must not leak the key (SEC-3)."""

import json
from pathlib import Path

import aiohttp
import pytest
from multidict import CIMultiDict, CIMultiDictProxy
from yarl import URL

from routes import benchmark_jobs

FAKE_KEY = "FAKEKEY-0123456789"


class _Stream:
    def __init__(self, lines: list[str]) -> None:
        self._lines = [f"{line}\n".encode() for line in lines]

    def __aiter__(self) -> "_Stream":
        return self

    async def __anext__(self) -> bytes:
        if not self._lines:
            raise StopAsyncIteration
        return self._lines.pop(0)


class _Process:
    def __init__(self, lines: list[str]) -> None:
        self.stdout = _Stream(lines)

    async def wait(self) -> int:
        return 1


def _leaky_lines() -> list[str]:
    url = URL(f"https://user:hunter2@api.example/v1?key={FAKE_KEY}")
    headers = CIMultiDictProxy(
        CIMultiDict({"x-goog-api-key": FAKE_KEY, "Authorization": f"Bearer {FAKE_KEY}"})
    )
    info = aiohttp.RequestInfo(url, "POST", headers, url)
    error = aiohttp.ClientResponseError(info, (), status=401, message="Unauthorized")
    return [
        "judge: starting",
        repr(error),
        f"aiohttp.client_exceptions.ClientResponseError: {error}",
        f"Authorization: Bearer {FAKE_KEY}",
        f"retrying GET https://api.example/v1?alt=sse&api_key={FAKE_KEY}",
        "judge: 3/10 done",
    ]


@pytest.mark.parametrize("surface", ["snapshot", "last_job_file"])
async def test_job_log_masks_secrets_from_subprocess_output(
    surface: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    last_job_file = tmp_path / "analysis" / "last_job.json"
    monkeypatch.setattr(benchmark_jobs, "LAST_JOB_FILE", last_job_file)
    monkeypatch.setattr(benchmark_jobs, "RESULTS_DIR", tmp_path / "results")
    job = benchmark_jobs._Job("judge", ["python", "-m", "benchmark"], {})
    job.proc = _Process(_leaky_lines())  # type: ignore[assignment]

    await benchmark_jobs._pump(job)

    shown = json.dumps(job.snapshot()) if surface == "snapshot" else last_job_file.read_text()
    assert FAKE_KEY not in shown
    assert "hunter2" not in shown
    assert "judge: starting" in shown
    assert "judge: 3/10 done" in shown
