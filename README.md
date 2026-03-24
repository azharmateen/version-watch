# version-watch

[![Built with Claude Code](https://img.shields.io/badge/Built%20with-Claude%20Code-blue?logo=anthropic&logoColor=white)](https://claude.ai/code)


API versioning manager: detect breaking changes, track deprecations, generate sunset plans.

## Features

- **Diff** two OpenAPI specs and classify changes as breaking or non-breaking
- **Deprecation tracking** with sunset date warnings
- **Sunset plan generation** with migration guide markdown
- **API linting** for versioning best practices
- **Multiple output formats**: terminal, JSON, markdown, PR description

## Install

```bash
pip install -e .
```

## Usage

```bash
# Compare two API versions
version-watch diff v1.yaml v2.yaml

# Show deprecated endpoints/fields
version-watch deprecated api.yaml

# Generate sunset migration plan
version-watch plan v1.yaml v2.yaml --sunset-date 2026-06-01

# Lint API spec for versioning best practices
version-watch lint api.yaml

# Output as JSON
version-watch diff v1.yaml v2.yaml --format json

# Output as markdown
version-watch diff v1.yaml v2.yaml --format markdown
```

## Breaking Change Detection

| Change Type | Classification |
|------------|---------------|
| Endpoint removed | Breaking |
| Required field added to request | Breaking |
| Response field removed | Breaking |
| Field type changed | Breaking |
| New optional request field | Non-breaking |
| New endpoint added | Non-breaking |
| New response field | Non-breaking |
| Description changed | Non-breaking |

## Lint Rules

- API must have version in URL path (`/v1/`, `/v2/`)
- Deprecated endpoints must have `x-sunset-date`
- Response schemas should include a `version` field
- Deprecated fields must have a `description` explaining the replacement

## License

MIT
