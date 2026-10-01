"""Unit tests for services/results_mapper.py -- pure logic, no I/O,
responsible for defensively parsing LLM JSON output onto Link objects.
"""
from models import Link
from services.results_mapper import ResultMapper
from services.scoring_service import ScoringService


class FakeLink:
    def __init__(self, url, score=None):
        self.url = url
        self.score = score
        self.relevance_type = None
        self.expansions = None


class TestMapResults:
    def test_applies_matching_entries(self):
        links = [FakeLink("https://a.com"), FakeLink("https://b.com")]
        results = {
            "https://a.com": {"score": 85, "relevance_type": "direct", "expansions": ["x"]},
            "https://b.com": {"score": 10, "relevance_type": "irrelevant", "expansions": []},
        }
        mapped = ResultMapper().map_results(results, links)
        assert mapped[0].score == 85
        assert mapped[0].relevance_type == "direct"
        assert mapped[0].expansions == ["x"]
        assert mapped[1].score == 10
        assert mapped[1].relevance_type == "irrelevant"

    def test_missing_link_gets_safe_defaults(self):
        # `results` must be a *non-empty* dict that simply lacks this
        # link's URL -- an empty dict short-circuits the whole method
        # before any per-link default logic runs (see the falsy-results
        # test below), so this needs a populated dict to actually
        # exercise the per-missing-link default path.
        links = [FakeLink("https://missing.com"), FakeLink("https://present.com")]
        results = {"https://present.com": {"score": 10, "relevance_type": "direct", "expansions": []}}
        mapped = ResultMapper().map_results(results, links)
        assert mapped[0].score == 0
        assert mapped[0].relevance_type == "irrelevant"
        assert mapped[0].expansions == []

    def test_missing_link_preserves_existing_nonzero_score(self):
        # `link.score = link.score or 0` -- an existing truthy score
        # survives a missing LLM entry rather than being reset to 0.
        links = [FakeLink("https://missing.com", score=42), FakeLink("https://present.com")]
        results = {"https://present.com": {"score": 10, "relevance_type": "direct", "expansions": []}}
        mapped = ResultMapper().map_results(results, links)
        assert mapped[0].score == 42

    def test_empty_results_dict_returns_links_unmodified_object(self):
        links = [FakeLink("https://a.com", score=7)]
        result = ResultMapper().map_results({}, links)
        assert result is links
        # {} is falsy -> hits the early `if not results` return, so the
        # link is untouched entirely (not even the per-link default path).
        assert result[0].score == 7

    def test_non_dict_results_returns_links_untouched(self):
        links = [FakeLink("https://a.com", score=99)]
        result = ResultMapper().map_results(None, links)
        assert result is links
        assert result[0].score == 99  # never touched at all -- early return

    def test_no_mutation_when_results_falsy_vs_default_when_empty_dict(self):
        # `None`/falsy results short-circuits entirely (link untouched);
        # an empty dict `{}` is still falsy too, so it also short-circuits.
        # Confirm both behave identically (both hit `if not results`).
        links_a = [FakeLink("https://a.com")]
        links_b = [FakeLink("https://a.com")]
        ResultMapper().map_results(None, links_a)
        ResultMapper().map_results({}, links_b)
        assert links_a[0].relevance_type is None
        assert links_b[0].relevance_type is None


class TestMapPartial:
    def test_only_touches_links_present_in_results(self):
        links = [FakeLink("https://a.com", score=1), FakeLink("https://b.com", score=2)]
        results = {"https://a.com": {"score": 99, "relevance_type": "direct", "expansions": []}}
        mapped = ResultMapper().map_partial(results, links)
        assert mapped[0].score == 99
        assert mapped[1].score == 2  # untouched, unlike map_results' "safe default" behavior

    def test_falsy_results_leaves_links_untouched(self):
        links = [FakeLink("https://a.com", score=5)]
        mapped = ResultMapper().map_partial({}, links)
        assert mapped[0].score == 5


class TestParseScore:
    def test_valid_int_within_range(self):
        assert ResultMapper()._parse_score(50) == 50

    def test_clamps_above_100(self):
        assert ResultMapper()._parse_score(500) == 100

    def test_clamps_below_0(self):
        assert ResultMapper()._parse_score(-20) == 0

    def test_numeric_string_coerced(self):
        assert ResultMapper()._parse_score("77") == 77

    def test_float_string_rejected_gracefully(self):
        # int("77.5") raises ValueError -- should degrade to 0, not crash.
        assert ResultMapper()._parse_score("77.5") == 0

    def test_none_defaults_to_zero(self):
        assert ResultMapper()._parse_score(None) == 0

    def test_garbage_string_defaults_to_zero(self):
        assert ResultMapper()._parse_score("not a number") == 0

    def test_dict_defaults_to_zero(self):
        assert ResultMapper()._parse_score({"nested": "json"}) == 0


class TestParseRelevanceType:
    def test_valid_lowercase(self):
        assert ResultMapper()._parse_relevance_type("direct") == "direct"

    def test_valid_uppercase_normalized(self):
        assert ResultMapper()._parse_relevance_type("DIRECT") == "direct"

    def test_invalid_value_becomes_ambiguous(self):
        assert ResultMapper()._parse_relevance_type("made_up_type") == "ambiguous"

    def test_non_string_becomes_ambiguous(self):
        assert ResultMapper()._parse_relevance_type(None) == "ambiguous"
        assert ResultMapper()._parse_relevance_type(42) == "ambiguous"

    def test_all_valid_types_accepted(self):
        for t in ResultMapper.VALID_RELEVANCE_TYPES:
            assert ResultMapper()._parse_relevance_type(t) == t


class TestParseExpansions:
    def test_valid_list_of_strings(self):
        assert ResultMapper()._parse_expansions(["a", "b"]) == ["a", "b"]

    def test_strips_whitespace(self):
        assert ResultMapper()._parse_expansions(["  a  ", "b\n"]) == ["a", "b"]

    def test_drops_empty_and_whitespace_only_strings(self):
        assert ResultMapper()._parse_expansions(["a", "", "   ", "b"]) == ["a", "b"]

    def test_drops_non_string_items(self):
        assert ResultMapper()._parse_expansions(["a", 5, None, {"x": 1}, "b"]) == ["a", "b"]

    def test_non_list_input_returns_empty(self):
        assert ResultMapper()._parse_expansions("not a list") == []
        assert ResultMapper()._parse_expansions(None) == []
        assert ResultMapper()._parse_expansions({"a": 1}) == []


# ---- ScoringService: URL prefix trimming + response normalization ----


def test_common_url_prefix_stops_at_path_boundary():
    links = [Link(url=f"https://h.org/wiki/{n}", anchor="", context="") for n in ("Insulin", "Insight")]
    assert ScoringService.common_url_prefix(links) == "https://h.org/wiki/"
    assert ScoringService.common_url_prefix(links[:1]) == ""


def test_list_response_with_shortened_urls_maps_back_onto_links():
    prefix = "https://h.org/wiki/"
    links = [Link(url=prefix + "A", anchor="", context=""), Link(url=prefix + "B", anchor="", context="")]
    raw = {"results": [{"url": "A", "score": 90, "relevance_type": "direct", "expansions": ["x"]}]}
    restored = ScoringService._restore_urls(raw, prefix)
    ResultMapper().map_results(restored, links)
    assert (links[0].score, links[0].relevance_type) == (90, "direct")
    assert links[1].relevance_type == "irrelevant"  # LLM skipped it


def test_dict_shaped_response_still_supported():
    raw = {"results": {"https://a.com": {"score": 33}}}
    assert ScoringService._restore_urls(raw, "") == {"https://a.com": {"score": 33}}


# ---- typed outcomes (P1.7) ----


class TestOutcomes:
    def test_counts_scored_missing_and_malformed(self):
        links = [FakeLink("https://a.com"), FakeLink("https://b.com"), FakeLink("https://c.com")]
        mapper = ResultMapper()
        mapper.map_results({"https://a.com": {"score": 5}, "https://b.com": "junk"}, links)
        assert mapper.outcomes == {"scored": 1, "malformed_entry": 1, "missing": 1}
        assert links[1].relevance_type == "ambiguous"

    def test_non_dict_response_is_counted(self):
        mapper = ResultMapper()
        mapper.map_results(None, [FakeLink("https://a.com")])
        mapper.map_results(["x"], [FakeLink("https://a.com")])
        assert mapper.outcomes["malformed_response"] == 2

    def test_map_partial_survives_non_dict_entry(self):
        links = [FakeLink("https://a.com")]
        mapper = ResultMapper()
        mapper.map_partial({"https://a.com": 7}, links)
        assert mapper.outcomes["malformed_entry"] == 1


class TestExpansionContract:
    def _service(self, send):
        import asyncio
        from unittest.mock import MagicMock
        from services.nlp_service import NLPService

        svc = NLPService.__new__(NLPService)
        svc.expansion_outcomes = __import__("services.llm_contracts", fromlist=["Outcomes"]).Outcomes()
        svc.prompt_builder = MagicMock(build=MagicMock(return_value="p"))
        svc.blueprint_id = "bp"
        svc.llm_type, svc.model_information = "t", "m"

        async def emit(_):
            pass

        svc._emit = emit
        svc.llm_handler = MagicMock(send=send)
        return svc, asyncio

    def test_junk_and_exceptions_yield_empty_seeds(self):
        async def junk(_):
            return "oops"

        async def boom(_):
            raise RuntimeError("down")

        for send, key in ((junk, "malformed_response"), (boom, "request_failed")):
            svc, asyncio = self._service(send)
            assert asyncio.run(svc.create_expansions("t", {})) == {"descriptions": []}
            assert svc.expansion_outcomes[key] == 1

    def test_valid_descriptions_are_cleaned(self):
        async def ok(_):
            return {"descriptions": [" a ", 3, "", "b"]}

        svc, asyncio = self._service(ok)
        assert asyncio.run(svc.create_expansions("t", {})) == {"descriptions": ["a", "b"]}
