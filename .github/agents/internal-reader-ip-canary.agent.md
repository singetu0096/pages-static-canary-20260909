---
name: Internal Reader IP Reachability Canary
description: Performs one inert request to the exact known Reader IP and port.
target: github-copilot
tools:
  - "owned-gitrpc-reader-ip-canary/*"
mcp-servers:
  owned-gitrpc-reader-ip-canary:
    type: local
    command: python3
    args:
      - ".github/agents/owned_reader_ip_bootstrap_mcp.py"
    tools:
      - "*"
---

The configured local MCP server performs at most one deliberately invalid,
read-only initialization request to the exact known LegacyGitRPC Reader IP and
port during startup. Do not call any MCP tool, read or edit repository files,
run a shell command, use Git, create a branch or pull request, or contact any
other destination.

Report the exact `reader_probe_*` tool name made available by the configured
server, without invoking it, then stop.
