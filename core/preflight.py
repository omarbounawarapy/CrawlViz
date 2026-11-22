"""Checks made before a crawl starts, so a missing key or a busy port is reported at once.

Each problem is a sentence that says what is wrong and what to do about it. Nothing
here reaches the network; the keys file is read only to see whether a key exists.
"""

import os
import socket
from pathlib import Path

from config import LLM_DEFAULT_ENDPOINTS
from config.runtime_config import RuntimeConfig
from infrastructure import KeyManager

# The host the live-graph WebSocket gateway binds (Crawler._build_ui_layer).
GATEWAY_HOST = "localhost"


def _provider_problem(provider: str, config: RuntimeConfig, keys_file: Path) -> str | None:
    """Why the blueprint's scoring provider cannot be called, or None when it can."""
    if provider not in LLM_DEFAULT_ENDPOINTS:
        supported = ", ".join(sorted(LLM_DEFAULT_ENDPOINTS))
        return (
            f"The blueprint scores pages with '{provider}', which CrawlViz does not support. "
            f"Choose one of {supported} in the blueprint's scoring settings."
        )
    own_server = config.providers.endpoints.get(provider) != LLM_DEFAULT_ENDPOINTS[provider]
    try:
        registry = KeyManager(keys_file=keys_file).registry
    except FileNotFoundError:
        registry = {}
    except ValueError as exc:
        return (
            f"The API keys file {keys_file} could not be read ({exc}). "
            "Fix the file, or add the keys again on the Configuration page."
        )
    if registry.get(provider) or own_server:
        return None
    return (
        f"The blueprint scores pages with {provider}, but no {provider} API key is saved. "
        f"Add one on the Configuration page, or point {provider} at your own server in the "
        "provider endpoints."
    )


def _port_problem(port: int) -> str | None:
    """Why the gateway cannot listen on ``port``, or None when it can."""
    with socket.socket() as probe:
        if os.name == "posix":
            # Match the gateway's own listener, so a port in TIME_WAIT counts as free.
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind((GATEWAY_HOST, port))
        except OSError:
            return (
                f"Port {port} is already in use, so the live graph cannot connect. "
                "Stop whatever is using it, or choose another port under Observability "
                "on the Configuration page."
            )
    return None


def find_preflight_problems(
    scoring_provider: str, config: RuntimeConfig, keys_file: Path, offline: bool
) -> list[str]:
    """Every reason the crawl cannot start right now, each in plain words.

    ``offline`` crawls use a scripted LLM, so they need no key. The checks read
    files and probe a port, so call this off the event loop.
    """
    problems = []
    if not offline:
        problems.append(_provider_problem(scoring_provider, config, keys_file))
    problems.append(_port_problem(config.observability.ui_port))
    return [problem for problem in problems if problem is not None]
