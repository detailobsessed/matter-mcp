# matter-mcp

[![ci](https://github.com/detailobsessed/matter-mcp/workflows/ci/badge.svg)](https://github.com/detailobsessed/matter-mcp/actions?query=workflow%3Aci)
[![release](https://github.com/detailobsessed/matter-mcp/workflows/release/badge.svg)](https://github.com/detailobsessed/matter-mcp/actions?query=workflow%3Arelease)
[![documentation](https://img.shields.io/badge/docs-mkdocs-708FCC.svg?style=flat)](https://detailobsessed.github.io/matter-mcp/)
[![Python 3.14+](https://img.shields.io/badge/python-3.14+-blue.svg)](https://www.python.org/downloads/)
[![codecov](https://codecov.io/github/detailobsessed/matter-mcp/graph/badge.svg)](https://codecov.io/github/detailobsessed/matter-mcp)

An MCP server for getmatter.com

## Branch protection

The CI workflow includes a `ci-pass` gate job that aggregates the status of all CI jobs.
Add a [branch protection rule](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-a-branch-protection-rule/managing-a-branch-protection-rule) for `main` requiring the **`ci-pass`** status check to pass before merging.
