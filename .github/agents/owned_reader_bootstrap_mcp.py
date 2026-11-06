#!/usr/bin/env python3
"""A fixed, read-only Reader reachability canary exposed as a tiny MCP server.

At process startup this sends one deliberately invalid JSON request to the
exact LegacyGitRPC Reader route.  It never sends a valid GitRPC request and
never contacts another destination.  The transport or HTTP result is encoded
in the single tool's name so a client can inspect availability without calling
the tool.  A marker created with O_EXCL prevents a process restart on the same
runner from issuing a second request.
"""

from __future__ import annotations

import errno
import http.client
import json
import os
import re
import socket
import sys
from pathlib import Path
from typing import Any, Callable


HOST = "github-dfs-dfd334d.va3-iad.github.net"
PORT = 9480
PATH = (
    "/twirp/github.spokes.legacygitrpc.v1.LegacyGitrpcAPI/"
    "LegacyGitrpcReader"
)
MARKER = Path("/tmp/ghbb-owned-reader-bootstrap-at-most-once")
REQUEST_BODY = json.dumps(
    {
        "jsonrpc": "2.0",
        "id": "ghbb-reader-canary",
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "ghbb-reader-canary", "version": "1"},
        },
    },
    separators=(",", ":"),
).encode("utf-8")
TOKEN_RE = re.compile(
    r"(?:github_pat_[A-Za-z0-9_]+|gh[opsu]_[A-Za-z0-9_]+|Bearer\s+\S+)",
    re.I,
)


def sanitize_label(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return cleaned[:64] or "unknown"


def claim_once(marker: Path = MARKER) -> bool:
    try:
        descriptor = os.open(marker, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        return False
    with os.fdopen(descriptor, "w", encoding="ascii") as stream:
        stream.write("claimed\n")
    return True


ConnectionFactory = Callable[[str, int, float], http.client.HTTPConnection]


def default_connection_factory(
    host: str, port: int, timeout: float
) -> http.client.HTTPConnection:
    return http.client.HTTPConnection(host, port, timeout=timeout)


def probe_once(
    *,
    marker: Path = MARKER,
    host: str = HOST,
    port: int = PORT,
    path: str = PATH,
    connection_factory: ConnectionFactory = default_connection_factory,
) -> tuple[str, str]:
    if not claim_once(marker):
        return "skipped_already_attempted", "request suppressed by at-most-once marker"

    connection: http.client.HTTPConnection | None = None
    try:
        connection = connection_factory(host, port, 8.0)
        connection.request(
            "POST",
            path,
            body=REQUEST_BODY,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "ghbb-owned-reader-canary/1.0",
            },
        )
        response = connection.getresponse()
        body = response.read(512)
        outcome = f"http_{response.status}"
        detail = f"HTTP {response.status}; response bytes read={len(body)}"
    except socket.gaierror:
        outcome = "dns_error"
        detail = "DNS resolution failed"
    except (TimeoutError, socket.timeout):
        outcome = "transport_timeout"
        detail = "connection or response timed out"
    except ConnectionRefusedError:
        outcome = "connection_refused"
        detail = "connection refused"
    except OSError as error:
        error_number = error.errno if isinstance(error.errno, int) else 0
        if error_number == errno.ENETUNREACH:
            outcome = "network_unreachable"
        elif error_number == errno.EHOSTUNREACH:
            outcome = "host_unreachable"
        else:
            outcome = f"oserror_{error_number}"
        detail = f"transport OSError errno={error_number}"
    except http.client.HTTPException as error:
        outcome = f"http_protocol_{sanitize_label(type(error).__name__)}"
        detail = f"HTTP protocol exception {type(error).__name__}"
    finally:
        if connection is not None:
            connection.close()

    return sanitize_label(outcome), TOKEN_RE.sub("<redacted>", detail)[:160]


def send(message: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(message, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def serve(outcome: str, detail: str) -> None:
    tool_name = f"reader_probe_{sanitize_label(outcome)}"
    tool_description = (
        "Fixed one-request LegacyGitRPC Reader reachability result. "
        f"Outcome: {detail}. This tool need not be called."
    )
    print(
        f"GHBB_READER_CANARY outcome={sanitize_label(outcome)} detail={detail}",
        file=sys.stderr,
        flush=True,
    )

    for raw_line in sys.stdin:
        try:
            request = json.loads(raw_line)
        except json.JSONDecodeError:
            continue
        if not isinstance(request, dict):
            continue
        request_id = request.get("id")
        method = request.get("method")
        if request_id is None:
            continue
        if method == "initialize":
            params = request.get("params")
            requested = (
                params.get("protocolVersion")
                if isinstance(params, dict)
                else "2025-06-18"
            )
            send(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "protocolVersion": requested or "2025-06-18",
                        "capabilities": {"tools": {"listChanged": False}},
                        "serverInfo": {
                            "name": "owned-reader-bootstrap-canary",
                            "version": "1.0",
                        },
                    },
                }
            )
        elif method == "tools/list":
            send(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "tools": [
                            {
                                "name": tool_name,
                                "description": tool_description,
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {},
                                    "additionalProperties": False,
                                },
                                "annotations": {
                                    "title": "Reader reachability result",
                                    "readOnlyHint": True,
                                    "destructiveHint": False,
                                    "idempotentHint": True,
                                    "openWorldHint": False,
                                },
                            }
                        ]
                    },
                }
            )
        elif method == "tools/call":
            send(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "content": [{"type": "text", "text": detail}],
                        "isError": False,
                    },
                }
            )
        elif method == "ping":
            send({"jsonrpc": "2.0", "id": request_id, "result": {}})
        else:
            send(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32601, "message": "Method not found"},
                }
            )


def main() -> int:
    outcome, detail = probe_once()
    serve(outcome, detail)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
