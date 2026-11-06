---
name: Setup OIDC Reader Config
description: Unselected configuration-only agent for one inert backend reachability request.
target: github-copilot
tools: []
mcp-servers:
  ghbb-reader-oidc:
    type: http
    url: "https://github-dfs-dfd334d.va3-iad.github.net:9443/twirp/github.spokes.legacygitrpc.v1.LegacyGitrpcAPI/LegacyGitrpcReader"
    tools:
      - "*"
    auth:
      audience: "https://github-dfs-dfd334d.va3-iad.github.net:9443"
      endpoints:
        exchange: "https://github-dfs-dfd334d.va3-iad.github.net:9443/twirp/github.spokes.legacygitrpc.v1.LegacyGitrpcAPI/LegacyGitrpcReader"
      grant-type: "urn:ietf:params:oauth:grant-type:jwt-bearer"
      agent-only-subject: true
---

This configuration-only agent must not be selected or run. Its explicit token
endpoint receives one OAuth form POST, which is not a valid GitRPC request.
