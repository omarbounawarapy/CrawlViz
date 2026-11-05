"""Offline mode: a crawl with no keys and no network.

``CRAWLVIZ_OFFLINE=1`` makes the run route build a crawl from three doubles: the
frozen ISI graph served as HTML, a scripted LLM, and the hashing embedding
engine. Agents, CI and the demo UI use it to run full crawls. Nothing here is
used when the variable is unset.
"""

from .session import OFFLINE_ENV_VAR, OfflineSession, build_offline_session, is_offline

__all__ = ["OFFLINE_ENV_VAR", "OfflineSession", "build_offline_session", "is_offline"]
