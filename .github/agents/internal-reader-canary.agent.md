---
name: Internal Reader Reachability Canary
description: Performs one inert MCP initialization against an exact read-only GitRPC endpoint.
tools:
  - "owned-gitrpc-reader-canary/*"
mcp-servers:
  owned-gitrpc-reader-canary:
    type: http
    url: "https://spokesd-production.service.gc-cus-02.github.net:10013/twirp/github.spokes.legacygitrpc.v1.LegacyGitrpcAPI/LegacyGitrpcReader"
    tools:
      - "*"
---

Initialize the configured `owned-gitrpc-reader-canary` MCP server exactly once.
Do not call any MCP tool, edit or read repository files, run a shell command,
use Git, create a branch or pull request, or contact any other destination.
Report only whether initialization reached an HTTP application response or
failed at DNS, connection, or timeout, then stop.
