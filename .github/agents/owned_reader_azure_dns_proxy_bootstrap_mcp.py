#!/usr/bin/env python3
"""Resolve one fixed GitHub proxy name through Azure DNS, then probe Reader.

Exactly one UDP DNS query is sent to Azure's fixed fabric resolver.  Only a
private IPv4 answer for the fixed regional GitHub proxy name is accepted.  If
one is returned, the existing bounded proxy bootstrap sends at most one
deliberately invalid Reader request through that address.  No credential,
valid GitRPC operation, repository selector, command, option, or Writer route
is present.
"""

from __future__ import annotations

import ipaddress
import socket
import struct
from pathlib import Path
from typing import Callable

import owned_reader_proxy_bootstrap_mcp as proxy
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
DNS_SERVER = "168.63.129.16"
DNS_PORT = 53
DNS_TRANSACTION_ID = 0x4748
MARKER = Path("/tmp/ghbb-owned-reader-azure-dns-proxy-at-most-once")
INNER_MARKER = Path("/tmp/ghbb-owned-reader-azure-dns-proxy-request-at-most-once")


def encode_name(name: str) -> bytes:
    labels = name.rstrip(".").split(".")
    if any(not label or len(label.encode("ascii")) > 63 for label in labels):
        raise ValueError("invalid fixed DNS name")
    return b"".join(
        bytes([len(label.encode("ascii"))]) + label.encode("ascii")
        for label in labels
    ) + b"\x00"


DNS_QUERY = (
    struct.pack("!HHHHHH", DNS_TRANSACTION_ID, 0x0100, 1, 0, 0, 0)
    + encode_name(HOST)
    + struct.pack("!HH", 1, 1)
)


def skip_name(message: bytes, offset: int) -> int:
    steps = 0
    while True:
        if offset >= len(message) or steps > 128:
            raise ValueError("truncated DNS name")
        length = message[offset]
        if length & 0xC0 == 0xC0:
            if offset + 1 >= len(message):
                raise ValueError("truncated DNS compression pointer")
            return offset + 2
        offset += 1
        if length == 0:
            return offset
        if length > 63 or offset + length > len(message):
            raise ValueError("invalid DNS label")
        offset += length
        steps += 1


def decode_a_records(message: bytes) -> tuple[int, list[str]]:
    if len(message) < 12:
        raise ValueError("truncated DNS header")
    transaction_id, flags, qdcount, ancount, _, _ = struct.unpack(
        "!HHHHHH", message[:12]
    )
    if transaction_id != DNS_TRANSACTION_ID or not flags & 0x8000:
        raise ValueError("unexpected DNS response identity")
    rcode = flags & 0x000F
    offset = 12
    for _ in range(qdcount):
        offset = skip_name(message, offset)
        if offset + 4 > len(message):
            raise ValueError("truncated DNS question")
        offset += 4

    addresses: list[str] = []
    for _ in range(ancount):
        offset = skip_name(message, offset)
        if offset + 10 > len(message):
            raise ValueError("truncated DNS answer")
        record_type, record_class, _, length = struct.unpack(
            "!HHIH", message[offset : offset + 10]
        )
        offset += 10
        if offset + length > len(message):
            raise ValueError("truncated DNS record data")
        data = message[offset : offset + length]
        offset += length
        if record_type == 1 and record_class == 1 and length == 4:
            addresses.append(socket.inet_ntoa(data))
    return rcode, addresses


SocketFactory = Callable[[], socket.socket]


def default_socket_factory() -> socket.socket:
    return socket.socket(socket.AF_INET, socket.SOCK_DGRAM)


def resolve_proxy_ip(
    socket_factory: SocketFactory = default_socket_factory,
) -> tuple[str, str | None, str]:
    resolver = socket_factory()
    try:
        resolver.settimeout(4.0)
        resolver.sendto(DNS_QUERY, (DNS_SERVER, DNS_PORT))
        response, source = resolver.recvfrom(2048)
    except (TimeoutError, socket.timeout):
        return "azure_dns_timeout", None, "Azure DNS query timed out"
    except OSError as error:
        number = error.errno if isinstance(error.errno, int) else 0
        return (
            f"azure_dns_oserror_{number}",
            None,
            f"Azure DNS transport OSError errno={number}",
        )
    finally:
        resolver.close()

    if source != (DNS_SERVER, DNS_PORT):
        return "azure_dns_unexpected_source", None, "Unexpected DNS response source"
    try:
        rcode, addresses = decode_a_records(response)
    except ValueError:
        return "azure_dns_invalid_response", None, "Invalid Azure DNS response"
    if rcode != 0:
        return f"azure_dns_rcode_{rcode}", None, f"Azure DNS returned rcode={rcode}"
    if not addresses:
        return "azure_dns_no_a", None, "Azure DNS returned no IPv4 answer"
    unique = sorted(set(addresses))
    if len(unique) != 1:
        return "azure_dns_multiple_a", None, "Azure DNS returned multiple IPv4 answers"
    address = ipaddress.ip_address(unique[0])
    if address.version != 4 or not address.is_private:
        return (
            "azure_dns_nonprivate_a",
            None,
            "Azure DNS answer was not a private IPv4 address",
        )
    return "azure_dns_private_a", str(address), "Azure DNS returned one private IPv4 answer"


def probe_once(*, marker: Path = MARKER) -> tuple[str, str]:
    if not claim_once(marker):
        return await_published_result(marker)

    dns_outcome, address, dns_detail = resolve_proxy_ip()
    if address is None:
        outcome = dns_outcome
        detail = dns_detail
    else:
        proxy_outcome, proxy_detail = proxy.probe_once(
            marker=INNER_MARKER,
            host=address,
            port=PORT,
        )
        outcome = f"azure_dns_private_a_{proxy_outcome}"
        detail = f"{dns_detail}; {proxy_detail}"

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
