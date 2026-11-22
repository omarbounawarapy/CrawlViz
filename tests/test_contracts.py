"""The duck-typed collaborators the pipelines consume match their declared Protocols."""

from crawlviz.events import Annotator, Fetcher, RelevanceScorer
from crawlviz.shared import NetworkClient
from services.nlp_service import NLPService
from services.scoring_service import ScoringService
from traceability.traced_network_client import TracedNetworkClient


def test_real_implementations_satisfy_the_contracts():
    assert issubclass(NLPService, RelevanceScorer)
    assert issubclass(ScoringService, Annotator)
    assert issubclass(NetworkClient, Fetcher)
    assert issubclass(TracedNetworkClient, Fetcher)
