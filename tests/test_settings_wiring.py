"""Every UI-editable setting must reach the object that uses it, persist,
and validate. Wiring is checked on a real Crawler built from a
non-default RuntimeConfig, so a setting that is declared but never read
fails here."""
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import routes.config as config_routes
import routes.run as run_routes
from config import settings_store as store
from config.paths import RuntimePaths
from priority.strategy import DEFAULT_WEIGHTS
from config.runtime_config import RuntimeConfig, default_runtime_config
from core.crawler import Crawler
from infrastructure.key_manager import KeyManager
from infrastructure.llm_handler import LlmHandler
from tests.test_event_wiring import FAKE_BLUEPRINT, Fake

OVERRIDES = {
    "fetch": {
        "min_delay": 2.5, "jitter_max": 0.7, "backoff_start": 0.5, "backoff_max": 20.0,
        "backoff_growth": 3.0, "backoff_success_decay": 0.25, "backoff_failure_decay": 0.75,
        "user_agent": "TestBot/9", "respect_robots": False, "accept_language": "fr",
        "extra_headers": {"X-Test": "1"},
    },
    "pipelines": {
        "filtering": {"workers": 2, "max_queue_size": 5},
        "priority": {"workers": 3},
        "transformation": {"workers": 5},
        "debugging": {"workers": 1},
        "requests": {"workers": 6},
        "scoring": {"workers": 2},
        "retry": {"workers": 2},
    },
    "retries": {"max_request_retries": 9, "max_scoring_retries": 8, "base_delay": 0.1,
                "growth": 3.0, "empty_score_demotion": 7, "fetch_retry_demotion": 4},
    "scoring_cascade": {"percentile_bucketing": False, "low_percentile": 10.0,
                        "high_percentile": 90.0, "percentile_min_links": 3,
                        "max_llm_links_per_node": 11, "llm_batch_size": 4},
    "priority": {"nlp_bias": 30, "llm_bias": 70},
    "observability": {"debug_enabled": False, "ui_port": 9001},
    "run": {"seed": 5},
}


def build(tmp_path, overrides=OVERRIDES):
    cfg = store.load_runtime_config(None, overrides)
    crawler = Crawler("wikiMD.json", config=cfg, paths=RuntimePaths.under(tmp_path))
    crawler._load_blueprint_config(FAKE_BLUEPRINT)
    return crawler, crawler._build_pipelines(FAKE_BLUEPRINT, Fake(), Fake())


def test_fetch_settings_reach_requests_pipeline(tmp_path):
    _, p = build(tmp_path)
    r = p["requests"]
    assert (r.min_delay, r.jitter_max, r.backoff_start, r.max_backoff) == (2.5, 0.7, 0.5, 20.0)
    assert (r.backoff_growth, r.backoff_success_decay, r.backoff_failure_decay) == (3.0, 0.25, 0.75)
    assert r.headers["User-Agent"] == "TestBot/9"
    assert r.headers["Accept-Language"] == "fr"
    assert r.headers["X-Test"] == "1"
    assert r.robots is None
    assert r.max_concurrency == 6
    assert r.network_client.total_timeout == 30


def test_worker_counts_reach_every_pipeline(tmp_path):
    crawler, p = build(tmp_path)
    assert p["filtering"].max_concurrency == 2
    assert p["filtering"].queue.maxsize == 5
    assert p["priority"].max_concurrency == 3
    assert p["transformation"].max_concurrency == 5
    assert p["debug"].max_concurrency == 1
    assert p["debug"].enabled is False
    assert p["scoring"].max_concurrency == 2
    assert p["retry"].max_concurrency == 2
    assert crawler.fetch_concurrency == 6 and crawler.ui_port == 9001 and crawler.seed == 5


def test_retry_cascade_priority_settings(tmp_path):
    _, p = build(tmp_path)
    rt = p["retry"]
    assert (rt.max_request_retries, rt.max_scoring_retries, rt.retry_base_delay) == (9, 8, 0.1)
    assert (rt.retry_growth, rt.empty_score_demotion, rt.fetch_retry_demotion) == (3.0, 7, 4)
    s = p["scoring"]
    assert s.percentile_bucketing is False and (s.low_percentile, s.high_percentile) == (10.0, 90.0)
    assert (s.percentile_min_links, s.max_llm_links, s.llm_batch_size) == (3, 11, 4)
    assert (p["priority"]._nlp_weight, p["priority"]._llm_weight) == (0.3, 0.7)


def test_defaults_keep_the_previous_behaviour(tmp_path):
    crawler, p = build(tmp_path, {})
    assert (p["filtering"].max_concurrency, p["priority"].max_concurrency) == (10, 10)
    assert (p["transformation"].max_concurrency, p["debug"].max_concurrency) == (3, 2)
    assert p["requests"].max_concurrency == 4 and p["scoring"].max_concurrency == 1
    assert p["requests"].min_delay == 1.0 and p["requests"].max_backoff == 10.0
    assert crawler.ui_port == 8765 and crawler.seed is None


def test_explicit_ctor_args_beat_config(tmp_path):
    cfg = store.load_runtime_config(None, OVERRIDES)
    c = Crawler("wikiMD.json", config=cfg, paths=RuntimePaths.under(tmp_path),
                fetch_concurrency=1, ui_port=1234, seed=2)
    assert (c.fetch_concurrency, c.ui_port, c.seed) == (1, 1234, 2)


@pytest.mark.parametrize("bad", [
    {"fetch": {"backoff_start": 5, "backoff_max": 1}},
    {"fetch": {"http_connect_timeout": 99, "http_total_timeout": 5}},
    {"scoring_cascade": {"low_percentile": 80, "high_percentile": 20}},
    {"scoring_cascade": {"low_threshold": 0.9, "high_threshold": 0.1}},
    {"pipelines": {"filtering": {"workers": 0}}},
    {"priority": {"nlp_bias": 0, "llm_bias": 0}},
])
def test_invalid_settings_are_rejected(bad):
    with pytest.raises(Exception):
        store.load_runtime_config(None, bad)


def test_store_persists_only_the_difference(tmp_path):
    f = tmp_path / "settings.json"
    store.save_settings(f, {"fetch": {"min_delay": 3.0}})
    assert json.loads(f.read_text()) == {"fetch": {"min_delay": 3.0}}
    store.save_settings(f, {"pipelines": {"filtering": {"workers": 4}}})
    cfg = store.load_runtime_config(f, {"fetch": {"min_delay": 0.0}})
    assert cfg.fetch.min_delay == 0.0                     # override beats stored
    assert cfg.pipelines.filtering.workers == 4           # stored beats default
    assert cfg.pipelines.priority.workers == 10           # untouched stays default
    store.reset_settings(f, "fetch")
    assert "fetch" not in json.loads(f.read_text())
    store.reset_settings(f)
    assert json.loads(f.read_text()) == {}


def test_invalid_save_writes_nothing(tmp_path):
    f = tmp_path / "settings.json"
    with pytest.raises(Exception):
        store.save_settings(f, {"fetch": {"min_delay": -1}})
    assert not f.exists()


def test_default_runtime_config_ignores_stored_settings(tmp_path):
    store.save_settings(tmp_path / "settings.json", {"fetch": {"min_delay": 9.0}})
    assert default_runtime_config().fetch.min_delay == 1.0


@pytest.fixture
def client(tmp_path, monkeypatch):
    paths = RuntimePaths.under(tmp_path)
    monkeypatch.setattr(config_routes, "default_runtime_paths", lambda: paths)
    monkeypatch.setattr(run_routes, "default_runtime_paths", lambda: paths)
    app = FastAPI()
    app.include_router(config_routes.router)
    return TestClient(app), paths


def test_config_routes_round_trip(client):
    c, paths = client
    r = c.put("/config", json={"values": {"fetch": {"user_agent": "UI/1"}}})
    assert r.status_code == 200 and r.json()["fetch"]["user_agent"] == "UI/1"
    assert c.get("/config").json()["fetch"]["user_agent"] == "UI/1"
    assert c.get("/config/defaults").json()["fetch"]["user_agent"] != "UI/1"
    assert c.get("/config/stored").json() == {"fetch": {"user_agent": "UI/1"}}
    assert c.post("/config/reset", params={"section": "fetch"}).status_code == 200
    assert c.get("/config/stored").json() == {}
    assert c.post("/config/reset", params={"section": "nope"}).status_code == 404


def test_config_validation_errors_are_structured(client):
    c, _ = client
    r = c.put("/config", json={"values": {"pipelines": {"filtering": {"workers": 0}}}})
    assert r.status_code == 422
    assert r.json()["detail"]["errors"][0]["path"].startswith("pipelines.filtering.workers")
    v = c.post("/config/validate", json={"values": {"fetch": {"min_delay": -1}}}).json()
    assert v["valid"] is False and v["errors"]


def test_schema_marks_apply_mode_and_widgets(client):
    c, _ = client
    schema = c.get("/config/schema").json()
    fetch = schema["$defs"]["FetchConfig"]["properties"]
    assert fetch["min_delay"]["ui_apply"] == "live"
    assert fetch["extra_headers"]["ui_widget"] == "headers"


def test_keys_are_masked_and_removable(client):
    c, paths = client
    secret = "sk-secret-value-1234"
    assert c.post("/keys", json={"provider": "groq", "key": secret}).status_code == 200
    listing = c.get("/keys")
    assert secret not in listing.text
    entry = listing.json()["groq"][0]
    assert entry["last4"] == "1234"
    assert json.loads(paths.keys_file.read_text())["groq"] == [secret]
    assert c.post("/keys", json={"provider": "nope", "key": "x"}).status_code == 422
    assert c.delete(f"/keys/groq/{entry['id']}").status_code == 200
    assert c.get("/keys").json() == {}
    assert c.delete("/keys/groq/missing").status_code == 404


def test_key_manager_cooldown_and_last_key_removal(tmp_path):
    f = tmp_path / "keys.json"
    f.write_text(json.dumps({"groq": ["aaaaaaaa"]}))
    km = KeyManager(cooldown=5, keys_file=f)
    assert km.cooldown == 5
    assert km.remove_key("groq", km.fingerprint("aaaaaaaa")) is True
    assert json.loads(f.read_text()) == {}


def test_llm_options_use_each_providers_request_shape():
    h = LlmHandler(KeyManager.__new__(KeyManager), client=object(), max_tokens=77, temperature=0.3)
    openai_like = {"data": {"model": "m", "messages": []}}
    h._apply_options("groq", openai_like)
    assert openai_like["data"]["max_tokens"] == 77 and openai_like["data"]["temperature"] == 0.3
    gemini = {"data": {"contents": []}}
    h._apply_options("gemini", gemini)
    assert gemini["data"]["generationConfig"] == {"maxOutputTokens": 77, "temperature": 0.3}
    plain = LlmHandler(KeyManager.__new__(KeyManager), client=object())
    untouched = {"data": {"model": "m"}}
    plain._apply_options("groq", untouched)
    assert untouched["data"] == {"model": "m"}


def test_run_overrides_are_validated(tmp_path, monkeypatch):
    paths = RuntimePaths.under(tmp_path)
    monkeypatch.setattr(run_routes, "default_runtime_paths", lambda: paths)
    tpl = tmp_path / "t"
    tpl.mkdir()
    monkeypatch.setattr(run_routes, "TEMPLATES_DIR", str(tpl))
    with open("templates/wikiMD.json", encoding="utf-8") as f:
        (tpl / "wikiMD.json").write_text(f.read())
    app = FastAPI()
    app.include_router(run_routes.router)
    c = TestClient(app)
    r = c.post("/run", json={"templateName": "wikiMD.json",
                             "overrides": {"fetch": {"min_delay": -5}}})
    assert r.status_code == 422
    assert isinstance(RuntimeConfig.model_validate({}), RuntimeConfig)


NEW_KNOBS = {
    "fetch": {"respect_robots": True, "robots_ttl_seconds": 30.0},
    "nlp": {"target_top_k": 4, "cluster_eps": 0.5, "cluster_min_samples": 3,
            "link_context_length": 40},
    "run": {"stop_check_interval": 0.5, "shutdown_grace": 1.5},
    "observability": {"snapshot_max_candidates": 7, "snapshot_max_errors": 3},
    "priority": {name + "_weights": {k: 0.0 for k in DEFAULT_WEIGHTS[name]} | {"target_similarity": 1.0}
                 for name in ("aggressive", "balanced", "exploration")},
}


def test_new_knobs_reach_their_objects(tmp_path):
    _, p = build(tmp_path, NEW_KNOBS)
    assert p["requests"].robots.ttl == 30.0
    assert p["processing"].link_context_length == 40
    assert p["stopping"].check_interval == 0.5

    class N:
        _nlp_vector = None

    class L:
        nlp_vector = {"target_similarity": 0.5, "novelty_injection": 0.9}
        score = None

    class Node:
        def get_depth(self):
            return 3

    # weights merge over the defaults, so the rest are zeroed
    assert p["priority"].strategy(Node(), L(), 1.0, 0.0) == 0.5


def test_snapshot_bounds_and_url_rules(tmp_path):
    from ui_bridge import CrawlStateSnapshot
    from utils.html_utils import configure_url_normalization, normalize_url

    snap = CrawlStateSnapshot(max_candidates=7, max_errors=3)
    assert snap._candidates.maxlen == 7 and snap._errors.maxlen == 3
    try:
        configure_url_normalization(strip_fragment=False, strip_trailing_slash=False)
        assert normalize_url("http://a.b/x/#y") == "http://a.b/x/#y"
    finally:
        configure_url_normalization()
    assert normalize_url("http://a.b/x/#y") == "http://a.b/x"


def test_nlp_knobs_reach_service():
    import inspect
    from services.nlp_service import NLPService
    sig = inspect.signature(NLPService.__init__).parameters
    assert {"target_top_k", "cluster_eps", "cluster_min_samples"} <= set(sig)


def test_unknown_priority_weight_rejected():
    with pytest.raises(Exception):
        store.load_runtime_config(None, {"priority": {"balanced_weights": {"bogus": 1}}})


def test_robots_ttl_refetches_after_expiry():
    import asyncio
    from pipelines.robots import RobotsPolicy

    class F:
        calls = 0

        async def emit_request(self, req):
            F.calls += 1
            return "User-agent: *\nDisallow: /no"

    async def run(ttl):
        F.calls = 0
        r = RobotsPolicy(F(), "ua", None, ttl)
        await r.allowed("http://h/x")
        r._loaded_at["http://h"] -= 100
        await r.allowed("http://h/x")
        return F.calls

    assert asyncio.run(run(0.0)) == 1
    assert asyncio.run(run(50.0)) == 2


def test_presets_export_and_token(client, monkeypatch):
    client = client[0]
    r = client.get("/config/presets")
    assert r.status_code == 200 and "polite" in r.json()["builtin"]
    assert client.put("/config", json={"values": {"fetch": {"min_delay": 4.0}}}).status_code == 200
    assert client.get("/config/export").json() == {"fetch": {"min_delay": 4.0}}
    assert client.put("/config/presets/mine").json() == {"saved": "mine"}
    assert client.put("/config/presets/polite").status_code == 422
    assert client.put("/config/presets/bad", json={"values": {"fetch": {"min_delay": -1}}}).status_code == 422
    assert client.post("/config/presets/fast/apply").json()["fetch"]["min_delay"] == 0.2
    assert client.post("/config/presets/mine/apply").json()["fetch"]["min_delay"] == 4.0
    assert client.delete("/config/presets/mine").status_code == 200
    assert client.post("/config/presets/mine/apply").status_code == 404

    monkeypatch.setenv("CRAWLVIZ_API_TOKEN", "s3cret")
    assert client.get("/config").status_code == 401
    assert client.get("/config", headers={"Authorization": "Bearer nope"}).status_code == 401
    assert client.get("/config", headers={"Authorization": "Bearer s3cret"}).status_code == 200
    assert client.get("/keys").status_code == 401


def test_prompts_and_endpoints_reach_their_objects(tmp_path):
    from models.prompts import PromptBuilder

    cfg = store.load_runtime_config(None, {
        "prompts": {"scoring_system": "SYS", "scoring_rules": "RULES:\n- only this",
                    "strategy_contexts": {"TOPICAL": "custom ctx"}},
        "providers": {"endpoints": {"groq": "http://localhost:9/v1/chat"}},
    })
    crawler = Crawler("wikiMD.json", config=cfg, paths=RuntimePaths.under(tmp_path))
    crawler._load_blueprint_config(FAKE_BLUEPRINT)
    pr = cfg.prompts
    text = PromptBuilder("cats", "TOPICAL", pr.scoring_system, pr.scoring_rules,
                         pr.strategy_contexts).build_prompt([])
    assert text.startswith("SYS") and "- only this" in text and "custom ctx" in text
    assert "OUTPUT FORMAT" in text and "Score range" not in text

    from infrastructure.llm_handler import LlmHandler
    h = LlmHandler(None, endpoints=cfg.providers.endpoints)
    assert h.endpoints == {"groq": "http://localhost:9/v1/chat"}
    params = {"url": "x"}
    ctx = type("C", (), {"get_model_information": lambda s: "m"})()
    h._apply_endpoint("groq", params, ctx)
    assert params["url"] == "http://localhost:9/v1/chat"


def test_invalid_prompt_and_endpoint_rejected():
    for bad in ({"prompts": {"scoring_system": ""}},
                {"prompts": {"strategy_contexts": {"NOPE": "x"}}},
                {"providers": {"endpoints": {"groq": "ftp://x"}}},
                {"providers": {"endpoints": {"mystery": "http://x"}}}):
        with pytest.raises(Exception):
            store.load_runtime_config(None, bad)


def test_running_crawl_sees_key_changes(tmp_path):
    f = tmp_path / "keys.json"
    f.write_text('{"groq": ["aaaaaaaa1111"]}')
    km = KeyManager(keys_file=f)
    f.write_text('{"groq": ["aaaaaaaa1111", "bbbbbbbb2222"], "openai": ["cccccccc3333"]}')
    km.reload()
    assert km.registry["groq"] == ["aaaaaaaa1111", "bbbbbbbb2222"]
    assert "openai" in km.registry and km.indexes["openai"] == 0
    f.write_text('{"openai": ["cccccccc3333"]}')
    km.reload()
    assert "groq" not in km.registry


def test_queue_bound_none_is_unbounded_and_legacy_zero_migrates(tmp_path):
    cfg = store.load_runtime_config(None, {"pipelines": {"filtering": {"max_queue_size": 0}}})
    assert cfg.pipelines.filtering.max_queue_size is None
    assert default_runtime_config().pipelines.requests.max_queue_size is None
    _, p = build(tmp_path, {"pipelines": {"filtering": {"max_queue_size": 5}}})
    assert p["filtering"].queue.maxsize == 5
    assert p["requests"].queue.maxsize == 0


def test_cascade_pair_hints_in_schema():
    props = RuntimeConfig.model_json_schema()["$defs"]["ScoringCascadeConfig"]["properties"]
    assert props["low_threshold"]["ui_pair"] == "high_threshold"
    assert props["high_percentile"]["ui_pair"] == "low_percentile"
    assert list(props)[0] == "percentile_bucketing"
