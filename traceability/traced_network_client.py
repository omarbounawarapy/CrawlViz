import time
import uuid

from traceability.trace_context import get_trace
from traceability.network_trace_events import (
    NET_RequestCreated,
    NET_RequestDispatched,
    NET_ResponseReceived,
    NET_RequestFailed,
)


class TracedNetworkClient:
    """
    Drop-in wrapper around NetworkClient.
    Emits NET_* trace events without modifying request/response logic.

    Usage in crawler.py
    -------------------
    from traceability.traced_network_client import TracedNetworkClient

    raw_client = NetworkClient()
    traced_client = TracedNetworkClient(raw_client, tracer)
    llm_handler = LlmHandler(key_manager, client=traced_client)
    """

    def __init__(self, inner, tracer):
        self._inner = inner
        self._tracer = tracer

    def __getattr__(self, name):
        return getattr(self._inner, name)

    async def emit_request(self, params: dict):
        trace_id, node_id = get_trace()
        request_id = uuid.uuid4().hex[:10]

        method = params.get("method", "GET").upper()
        url = params.get("url", "")
        headers = params.get("headers") or {}
        has_auth = any(k.lower() in ("authorization", "x-api-key") for k in headers)

        await self._tracer.emit(NET_RequestCreated(
            trace_id=trace_id,
            node_id=node_id,
            request_id=request_id,
            method=method,
            url=url,
            has_auth_header=has_auth,
        ))

        strategy_name = (
            "PostRequestStrategy" if method == "POST" else "GetRequestStrategy"
        )
        await self._tracer.emit(NET_RequestDispatched(
            trace_id=trace_id,
            node_id=node_id,
            request_id=request_id,
            strategy_class=strategy_name,
        ))

        t0 = time.monotonic()
        try:
            response = await self._inner.emit_request(params)
            latency_ms = (time.monotonic() - t0) * 1000

            # Response size heuristic — works for str/dict/bytes
            if isinstance(response, (str, bytes)):
                size = len(response)
            elif isinstance(response, dict):
                size = len(str(response))
            else:
                size = 0

            await self._tracer.emit(NET_ResponseReceived(
                trace_id=trace_id,
                node_id=node_id,
                request_id=request_id,
                status_code=200,            # aiohttp already raised on non-2xx
                response_size_bytes=size,
                latency_ms=latency_ms,
            ))
            return response

        except Exception as exc:
            latency_ms = (time.monotonic() - t0) * 1000
            # Classify the error type
            exc_name = type(exc).__name__
            if "Timeout" in exc_name:
                error_type = "timeout"
            elif "ClientConnector" in exc_name or "Connection" in exc_name:
                error_type = "connection"
            elif "ClientResponse" in exc_name or "HTTPError" in exc_name:
                error_type = "http_error"
            else:
                error_type = "unknown"

            status_code = getattr(exc, "status", None)

            await self._tracer.emit(NET_RequestFailed(
                trace_id=trace_id,
                node_id=node_id,
                request_id=request_id,
                error_type=error_type,
                error_message=str(exc),
                status_code=status_code,
            ))
            raise

    async def close(self) -> None:
        await self._inner.close()