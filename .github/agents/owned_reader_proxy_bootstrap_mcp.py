#!/usr/bin/env python3
"""One fixed Reader reachability request through GitHub's regional proxy.

The process connects only to the fixed regional network-proxy service and
sends one absolute-form HTTP request for the exact LegacyGitRPC Reader route.
The body is deliberately not a valid LegacyGitRPC request.  It contains no
credential, repository selector, command, option, or Writer route.  The
result is exposed as a result-only MCP tool name.
"""

from __future__ import annotations

import errno
import http.client
import json
import socket
from pathlib import Path
from typing import Callable

from owned_reader_bootstrap_mcp import (
    TOKEN_RE,
    await_published_result,
    claim_once,
    publish_result,
    sanitize_label,
    serve,
)


HOST = "network-proxy.service.gc-cus-02.github.net"
PORT = 3128
TARGET_AUTHORITY = "github-dfs-dfd334d.va3-iad.github.net:9480"
TARGET_URL = (
    "http://github-dfs-dfd334d.va3-iad.github.net:9480/"
    "twirp/github.spokes.legacygitrpc.v1.LegacyGitrpcAPI/"
    "LegacyGitrpcReader"
)
MARKER = Path("/tmp/ghbb-owned-reader-proxy-bootstrap-at-most-once")
REQUEST_BODY = json.dumps(
    {
        "jsonrpc": "2.0",
        "id": "ghbb-reader-proxy-canary",
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "ghbb-reader-proxy-canary", "version": "1"},
        },
    },
    separators=(",", ":"),
).encode("utf-8")


ConnectionFactory = Callable[[str, int, float], http.client.HTTPConnection]


def default_connection_factory(
    host: str, port: int, timeout: float
) -> http.client.HTTPConnection:
    return http.client.HTTPConnection(host, port, timeout=timeout)


def proxy_generated_response(
    status: int, headers: dict[str, str]
) -> bool:
    if "x-squid-error" in headers or status == 407:
        return True
    return status in {502, 503, 504} and any(
        name in headers for name in ("via", "proxy-agent")
    )


def probe_once(
    *,
    marker: Path = MARKER,
    host: str = HOST,
    port: int = PORT,
    connection_factory: ConnectionFactory = default_connection_factory,
) -> tuple[str, str]:
    if not claim_once(marker):
        return await_published_result(marker)

    connection: http.client.HTTPConnection | None = None
    try:
        connection = connection_factory(host, port, 8.0)
        connection.request(
            "POST",
            TARGET_URL,
            body=REQUEST_BODY,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Host": TARGET_AUTHORITY,
                "User-Agent": "ghbb-owned-reader-proxy-canary/1.0",
            },
        )
        response = connection.getresponse()
        body = response.read(512)
        headers = {name.lower(): value for name, value in response.getheaders()}
        if proxy_generated_response(response.status, headers):
            outcome = f"proxy_http_{response.status}"
            detail = (
                f"HTTP proxy returned {response.status}; "
                f"response bytes read={len(body)}"
            )
        else:
            outcome = f"target_http_{response.status}"
            detail = (
                f"Target HTTP {response.status}; "
                f"response bytes read={len(body)}"
            )
    except socket.gaierror:
        outcome = "proxy_dns_error"
        detail = "Regional proxy DNS resolution failed"
    except (TimeoutError, socket.timeout):
        outcome = "proxy_transport_timeout"
        detail = "Regional proxy connection or response timed out"
    except ConnectionRefusedError:
        outcome = "proxy_connection_refused"
        detail = "Regional proxy connection refused"
    except OSError as error:
        error_number = error.errno if isinstance(error.errno, int) else 0
        if error_number == errno.ENETUNREACH:
            outcome = "proxy_network_unreachable"
        elif error_number == errno.EHOSTUNREACH:
            outcome = "proxy_host_unreachable"
        else:
            outcome = f"proxy_oserror_{error_number}"
        detail = f"Regional proxy transport OSError errno={error_number}"
    except http.client.HTTPException as error:
        outcome = f"proxy_http_protocol_{sanitize_label(type(error).__name__)}"
        detail = f"Regional proxy HTTP exception {type(error).__name__}"
    finally:
        if connection is not None:
            connection.close()

    safe_outcome = sanitize_label(outcome)
    safe_detail = TOKEN_RE.sub("<redacted>", detail)[:160]
    publish_result(marker, safe_outcome, safe_detail)
    return safe_outcome, safe_detail


def main() -> int:
    outcome, detail = probe_once()
    serve(outcome, detail)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
