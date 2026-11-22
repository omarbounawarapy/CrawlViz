"""The run manifest: what a crawl was started with, written beside its event log."""

from dataclasses import dataclass
from typing import Any

from config.runtime_config import RuntimeConfig
from crawlviz.contracts import dump_run_manifest
from ui_bridge.event_recorder import EventRecorder, git_sha

from .manifest_redaction import redact_manifest


@dataclass(frozen=True)
class RunManifestWriter:
    """Collects the inputs of one crawl and writes them, with secrets removed, as its manifest."""

    crawl_id: str
    # The blueprint is JSON loaded from a template file.
    blueprint: dict[str, Any]
    config: RuntimeConfig
    model_information: Any
    seed: int | None
    fetch_concurrency: int
    scoring_concurrency: int

    def build(self) -> dict[str, Any]:
        return {
            "crawl_id": self.crawl_id,
            "blueprint": self.blueprint,
            "runtime_config": self.config.model_dump(mode="json"),
            "embedding_model": self.config.embeddings.model_name,
            "llm_model": self.model_information,
            "git_sha": git_sha(),
            "seed": self.seed,
            "fetch_concurrency": self.fetch_concurrency,
            "scoring_concurrency": self.scoring_concurrency,
        }

    def write(self, recorder: EventRecorder) -> None:
        recorder.write_manifest(dump_run_manifest(redact_manifest(self.build())))
