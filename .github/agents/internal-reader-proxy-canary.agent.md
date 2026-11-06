---
name: Internal Reader Proxy Reachability Canary
description: Performs one inert Reader request through an exact regional GitHub network proxy.
target: github-copilot
tools:
  - "owned-gitrpc-reader-proxy-canary/*"
mcp-servers:
  owned-gitrpc-reader-proxy-canary:
    type: local
    command: python3
    args:
      - ".github/agents/owned_reader_proxy_bootstrap_mcp.py"
    tools:
      - "*"
---

The configured local MCP server performs at most one deliberately invalid,
read-only initialization request to the fixed LegacyGitRPC Reader route through
the fixed regional GitHub network proxy during startup.
Do not call any MCP tool, read or edit repository files, run a shell command,
use Git, create a branch or pull request, or contact any destination.

Report the exact `reader_probe_*` tool name made available by the configured
server, without invoking it, then stop.
