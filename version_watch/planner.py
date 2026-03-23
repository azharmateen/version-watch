"""Sunset plan generator: create migration guides from breaking changes."""

from __future__ import annotations

from datetime import date, timedelta

from .differ import DiffResult, Severity


def _versioning_strategy_recommendation(old_spec: dict, new_spec: dict) -> str:
    """Suggest versioning strategy based on spec analysis."""
    old_paths = list(old_spec.get("paths", {}).keys())
    new_paths = list(new_spec.get("paths", {}).keys())

    # Check if URL versioning is already used
    has_url_version = any("/v" in p for p in old_paths + new_paths)

    old_servers = old_spec.get("servers", [])
    has_server_version = any("/v" in s.get("url", "") for s in old_servers)

    if has_url_version or has_server_version:
        return "url-path"

    # Check for header versioning hints
    for path_item in old_spec.get("paths", {}).values():
        for method_data in path_item.values():
            if isinstance(method_data, dict):
                for param in method_data.get("parameters", []):
                    if param.get("in") == "header" and "version" in param.get("name", "").lower():
                        return "header"

    return "url-path"


def generate_sunset_plan(
    old_spec: dict,
    new_spec: dict,
    diff_result: DiffResult,
    sunset_date: date | None = None,
) -> str:
    """Generate a markdown migration guide from diff results."""
    if sunset_date is None:
        sunset_date = date.today() + timedelta(days=180)

    old_version = old_spec.get("info", {}).get("version", "old")
    new_version = new_spec.get("info", {}).get("version", "new")
    strategy = _versioning_strategy_recommendation(old_spec, new_spec)

    lines: list[str] = []
    lines.append(f"# API Migration Guide: v{old_version} -> v{new_version}")
    lines.append("")
    lines.append(f"**Sunset Date:** {sunset_date.isoformat()}")
    lines.append(f"**Days Until Sunset:** {(sunset_date - date.today()).days}")
    lines.append("")

    # Summary
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- **Breaking changes:** {len(diff_result.breaking)}")
    lines.append(f"- **Non-breaking changes:** {len(diff_result.non_breaking)}")
    lines.append(f"- **Info changes:** {len(diff_result.info)}")
    lines.append("")

    # Versioning strategy
    lines.append("## Versioning Strategy")
    lines.append("")
    if strategy == "url-path":
        lines.append("**Recommended: URL Path Versioning**")
        lines.append("")
        lines.append("```")
        lines.append(f"# Old: /v{old_version}/resource")
        lines.append(f"# New: /v{new_version}/resource")
        lines.append("```")
        lines.append("")
        lines.append("Both versions will run in parallel until the sunset date.")
    elif strategy == "header":
        lines.append("**Current: Header Versioning**")
        lines.append("")
        lines.append("```")
        lines.append(f"# Old: Accept-Version: {old_version}")
        lines.append(f"# New: Accept-Version: {new_version}")
        lines.append("```")
    else:
        lines.append("**Recommended: Query Parameter Versioning**")
        lines.append("")
        lines.append("```")
        lines.append(f"# Old: /resource?api-version={old_version}")
        lines.append(f"# New: /resource?api-version={new_version}")
        lines.append("```")
    lines.append("")

    # Breaking changes detail
    if diff_result.breaking:
        lines.append("## Breaking Changes (Action Required)")
        lines.append("")
        for i, change in enumerate(diff_result.breaking, 1):
            lines.append(f"### {i}. {change.description}")
            lines.append("")
            lines.append(f"**Path:** `{change.path}`")
            lines.append("")
            if change.old_value:
                lines.append(f"- **Old:** `{change.old_value}`")
            if change.new_value:
                lines.append(f"- **New:** `{change.new_value}`")
            lines.append("")
            # Generate migration hint
            desc_lower = change.description.lower()
            if "removed" in desc_lower:
                lines.append("**Migration:** Remove usage of this from your client code. "
                             "Check for any dependent logic.")
            elif "type changed" in desc_lower:
                lines.append("**Migration:** Update your client models to use the new type. "
                             "Add type conversion logic if needed.")
            elif "required" in desc_lower:
                lines.append("**Migration:** Ensure your requests include this field. "
                             "Update request builders and tests.")
            else:
                lines.append("**Migration:** Review the change and update your client code accordingly.")
            lines.append("")

    # Non-breaking changes
    if diff_result.non_breaking:
        lines.append("## Non-Breaking Changes (No Action Required)")
        lines.append("")
        for change in diff_result.non_breaking:
            lines.append(f"- **{change.path}**: {change.description}")
        lines.append("")

    # Timeline
    lines.append("## Migration Timeline")
    lines.append("")
    announce_date = date.today()
    deprecation_date = announce_date + timedelta(days=30)
    warning_date = sunset_date - timedelta(days=30)
    lines.append(f"| Phase | Date | Action |")
    lines.append(f"|-------|------|--------|")
    lines.append(f"| Announcement | {announce_date.isoformat()} | New version available, migration guide published |")
    lines.append(f"| Deprecation | {deprecation_date.isoformat()} | Old version marked deprecated, sunset headers added |")
    lines.append(f"| Warning | {warning_date.isoformat()} | Final warning: 30 days until shutdown |")
    lines.append(f"| Sunset | {sunset_date.isoformat()} | Old version endpoints return 410 Gone |")
    lines.append("")

    # Checklist
    lines.append("## Migration Checklist")
    lines.append("")
    lines.append("- [ ] Review all breaking changes above")
    lines.append("- [ ] Update API client library / SDK")
    lines.append("- [ ] Update request/response models")
    lines.append("- [ ] Run integration tests against new version")
    lines.append("- [ ] Update API documentation references")
    lines.append("- [ ] Monitor error rates after switch")
    lines.append(f"- [ ] Complete migration before {sunset_date.isoformat()}")
    lines.append("")

    return "\n".join(lines)
