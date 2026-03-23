"""Generate API changelogs from spec diffs.

Groups changes by version with breaking change indicators.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from .differ import Change, DiffResult, Severity


def _format_change_md(change: Change, bullet: str = "-") -> str:
    """Format a single change as a markdown list item."""
    icon = ""
    if change.severity == Severity.BREAKING:
        icon = "**BREAKING** "
    parts = [f"{bullet} {icon}{change.description}"]
    if change.old_value and change.new_value:
        parts[0] += f" (`{change.old_value}` -> `{change.new_value}`)"
    elif change.old_value:
        parts[0] += f" (was: `{change.old_value}`)"
    return parts[0]


def _categorize_changes(changes: list[Change]) -> dict[str, list[Change]]:
    """Group changes by category based on their path/description."""
    categories: dict[str, list[Change]] = {
        "Endpoints": [],
        "Parameters": [],
        "Request Body": [],
        "Response": [],
        "Other": [],
    }

    for change in changes:
        desc_lower = change.description.lower()
        path_lower = change.path.lower()

        if "endpoint" in desc_lower:
            categories["Endpoints"].append(change)
        elif "parameter" in desc_lower or "parameters" in path_lower:
            categories["Parameters"].append(change)
        elif "request" in path_lower or "request" in desc_lower:
            categories["Request Body"].append(change)
        elif "response" in path_lower or "response" in desc_lower:
            categories["Response"].append(change)
        else:
            categories["Other"].append(change)

    return {k: v for k, v in categories.items() if v}


def generate_changelog(
    diff_result: DiffResult,
    old_version: str = "",
    new_version: str = "",
    release_date: date | None = None,
) -> str:
    """Generate a markdown changelog from diff results."""
    if release_date is None:
        release_date = date.today()

    lines: list[str] = []

    # Header
    if new_version:
        lines.append(f"## [{new_version}] - {release_date.isoformat()}")
    else:
        lines.append(f"## [Unreleased] - {release_date.isoformat()}")
    lines.append("")

    if not diff_result.total_changes:
        lines.append("No changes detected.")
        return "\n".join(lines)

    # Summary line
    parts = []
    if diff_result.breaking:
        parts.append(f"{len(diff_result.breaking)} breaking")
    if diff_result.non_breaking:
        parts.append(f"{len(diff_result.non_breaking)} non-breaking")
    if diff_result.info:
        parts.append(f"{len(diff_result.info)} informational")
    lines.append(f"> {', '.join(parts)} change(s)")
    lines.append("")

    # Breaking changes first
    if diff_result.breaking:
        lines.append("### Breaking Changes")
        lines.append("")
        categorized = _categorize_changes(diff_result.breaking)
        for category, changes in categorized.items():
            if len(categorized) > 1:
                lines.append(f"#### {category}")
                lines.append("")
            for change in changes:
                lines.append(_format_change_md(change))
            lines.append("")

    # Non-breaking additions/changes
    added = [c for c in diff_result.non_breaking if "added" in c.description.lower()]
    changed = [c for c in diff_result.non_breaking if "added" not in c.description.lower()]

    if added:
        lines.append("### Added")
        lines.append("")
        for change in added:
            lines.append(_format_change_md(change))
        lines.append("")

    if changed:
        lines.append("### Changed")
        lines.append("")
        for change in changed:
            lines.append(_format_change_md(change))
        lines.append("")

    # Deprecations
    deprecations = [c for c in diff_result.info if "deprecated" in c.description.lower()]
    other_info = [c for c in diff_result.info if "deprecated" not in c.description.lower()]

    if deprecations:
        lines.append("### Deprecated")
        lines.append("")
        for change in deprecations:
            lines.append(_format_change_md(change))
        lines.append("")

    if other_info:
        lines.append("### Notes")
        lines.append("")
        for change in other_info:
            lines.append(_format_change_md(change))
        lines.append("")

    return "\n".join(lines)


def generate_full_changelog(
    entries: list[dict[str, Any]],
    title: str = "API Changelog",
) -> str:
    """Generate a full changelog from multiple version entries.

    Each entry should have:
        - version: str
        - date: str (ISO format)
        - diff_result: DiffResult
    """
    lines = [f"# {title}", ""]
    lines.append("All notable changes to this API will be documented in this file.")
    lines.append("")
    lines.append("The format follows [Keep a Changelog](https://keepachangelog.com/).")
    lines.append("")

    for entry in entries:
        version = entry.get("version", "Unreleased")
        release_date_str = entry.get("date", date.today().isoformat())
        try:
            release_date = date.fromisoformat(release_date_str)
        except (ValueError, TypeError):
            release_date = date.today()
        diff_result = entry["diff_result"]
        lines.append(generate_changelog(diff_result, new_version=version, release_date=release_date))
        lines.append("---")
        lines.append("")

    return "\n".join(lines)
