---
name: Internal Reader Azure DNS Proxy Canary
description: Resolves one fixed regional proxy name through Azure DNS and performs one inert Reader request only for a private answer.
target: github-copilot
tools:
  - "owned-gitrpc-reader-azure-dns-proxy-canary/*"
mcp-servers:
  owned-gitrpc-reader-azure-dns-proxy-canary:
    type: local
    command: python3
    args:
      - ".github/agents/owned_reader_azure_dns_proxy_bootstrap_mcp.py"
    tools:
      - "*"
---

The configured local MCP server sends one fixed DNS query to Azure's fabric
resolver. Only if that query returns one private IPv4 address for the fixed
regional GitHub proxy name does it perform at most one deliberately invalid,
read-only initialization request to the fixed LegacyGitRPC Reader route.
Do not call any MCP tool, read or edit repository files, run a shell command,
use Git, create a branch or pull request, or contact any other destination.

Report the exact `reader_probe_*` tool name made available by the configured
server, without invoking it, then stop.
