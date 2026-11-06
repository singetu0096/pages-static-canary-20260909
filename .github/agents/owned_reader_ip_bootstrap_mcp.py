#!/usr/bin/env python3
"""One fixed invalid Reader request to the known Reader IP address."""

from __future__ import annotations

from pathlib import Path

from owned_reader_bootstrap_mcp import probe_once, serve


HOST = "10.48.38.52"
PORT = 9480
MARKER = Path("/tmp/ghbb-owned-reader-ip-bootstrap-at-most-once")


def main() -> int:
    outcome, detail = probe_once(marker=MARKER, host=HOST, port=PORT)
    serve(outcome, detail)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
