"""Reports: terminal diff, JSON, markdown changelog, PR description."""

from __future__ import annotations

import json

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .differ import DiffResult, Severity
from .deprecation import DeprecationEntry
from .linter import LintIssue, LintLevel


# ---------------------------------------------------------------------------
# Diff reports
# ---------------------------------------------------------------------------

def print_diff_terminal(result: DiffResult, console: Console | None = None) -> None:
    """Print a colored diff report to the terminal."""
    console = console or Console()

    # Summary panel
    summary = Text()
    summary.append(f"Breaking: {len(result.breaking)}", style="bold red")
    summary.append(" | ")
    summary.append(f"Non-breaking: {len(result.non_breaking)}", style="bold green")
    summary.append(" | ")
    summary.append(f"Info: {len(result.info)}", style="bold blue")
    console.print(Panel(summary, title="API Diff Summary", border_style="cyan"))

    if result.breaking:
        table = Table(title="Breaking Changes", border_style="red")
        table.add_column("Path", style="bold")
        table.add_column("Description")
        table.add_column("Old", style="red")
        table.add_column("New", style="green")
        for c in result.breaking:
            table.add_row(c.path, c.description, str(c.old_value or ""), str(c.new_value or ""))
        console.print(table)

    if result.non_breaking:
        table = Table(title="Non-Breaking Changes", border_style="green")
        table.add_column("Path", style="bold")
        table.add_column("Description")
        for c in result.non_breaking:
            table.add_row(c.path, c.description)
        console.print(table)

    if result.info:
        table = Table(title="Info", border_style="blue")
        table.add_column("Path", style="bold")
        table.add_column("Description")
        for c in result.info:
            table.add_row(c.path, c.description)
        console.print(table)


def diff_to_json(result: DiffResult) -> str:
    """Return diff result as JSON string."""
    return json.dumps(result.to_dict(), indent=2)


def diff_to_markdown(result: DiffResult) -> str:
    """Return diff result as markdown changelog."""
    lines: list[str] = []
    lines.append("# API Changelog")
    lines.append("")
    lines.append(f"**Total changes:** {result.total_changes}")
    lines.append("")

    if result.breaking:
        lines.append("## Breaking Changes")
        lines.append("")
        for c in result.breaking:
            lines.append(f"- **`{c.path}`**: {c.description}")
            if c.old_value:
                lines.append(f"  - Old: `{c.old_value}`")
            if c.new_value:
                lines.append(f"  - New: `{c.new_value}`")
        lines.append("")

    if result.non_breaking:
        lines.append("## Non-Breaking Changes")
        lines.append("")
        for c in result.non_breaking:
            lines.append(f"- **`{c.path}`**: {c.description}")
        lines.append("")

    if result.info:
        lines.append("## Info")
        lines.append("")
        for c in result.info:
            lines.append(f"- **`{c.path}`**: {c.description}")
        lines.append("")

    return "\n".join(lines)


def diff_to_pr_description(result: DiffResult) -> str:
    """Generate a PR description from the diff."""
    lines: list[str] = []
    lines.append("## API Changes")
    lines.append("")

    if result.has_breaking:
        lines.append("**WARNING: This PR contains breaking API changes.**")
        lines.append("")

    lines.append(f"| Category | Count |")
    lines.append(f"|----------|-------|")
    lines.append(f"| Breaking | {len(result.breaking)} |")
    lines.append(f"| Non-breaking | {len(result.non_breaking)} |")
    lines.append(f"| Info | {len(result.info)} |")
    lines.append("")

    if result.breaking:
        lines.append("### Breaking Changes")
        lines.append("")
        for c in result.breaking:
            lines.append(f"- `{c.path}`: {c.description}")
        lines.append("")

    if result.non_breaking:
        lines.append("### Non-Breaking Changes")
        lines.append("")
        for c in result.non_breaking:
            lines.append(f"- `{c.path}`: {c.description}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Deprecation reports
# ---------------------------------------------------------------------------

def print_deprecations_terminal(entries: list[DeprecationEntry], console: Console | None = None) -> None:
    """Print deprecation report to terminal."""
    console = console or Console()

    if not entries:
        console.print("[green]No deprecated items found.[/green]")
        return

    table = Table(title="Deprecated Items", border_style="yellow")
    table.add_column("Path", style="bold")
    table.add_column("Kind")
    table.add_column("Description")
    table.add_column("Sunset Date")
    table.add_column("Urgency")

    urgency_styles = {
        "expired": "bold red",
        "critical": "red",
        "warning": "yellow",
        "ok": "green",
        "unknown": "dim",
    }

    for entry in entries:
        urgency_style = urgency_styles.get(entry.urgency, "dim")
        table.add_row(
            entry.path,
            entry.kind,
            entry.description[:60],
            entry.sunset_date.isoformat() if entry.sunset_date else "None",
            Text(entry.urgency, style=urgency_style),
        )

    console.print(table)


def deprecations_to_json(entries: list[DeprecationEntry]) -> str:
    """Return deprecation entries as JSON."""
    return json.dumps([e.to_dict() for e in entries], indent=2)


# ---------------------------------------------------------------------------
# Lint reports
# ---------------------------------------------------------------------------

def print_lint_terminal(issues: list[LintIssue], console: Console | None = None) -> None:
    """Print lint results to terminal."""
    console = console or Console()

    if not issues:
        console.print("[green]No lint issues found. API spec looks good![/green]")
        return

    errors = [i for i in issues if i.level == LintLevel.ERROR]
    warnings = [i for i in issues if i.level == LintLevel.WARNING]
    infos = [i for i in issues if i.level == LintLevel.INFO]

    table = Table(title="API Lint Results", border_style="yellow")
    table.add_column("Rule", style="bold")
    table.add_column("Level")
    table.add_column("Path")
    table.add_column("Message")

    level_styles = {
        LintLevel.ERROR: "bold red",
        LintLevel.WARNING: "yellow",
        LintLevel.INFO: "blue",
    }

    for issue in issues:
        style = level_styles.get(issue.level, "dim")
        table.add_row(
            issue.rule,
            Text(issue.level.value, style=style),
            issue.path,
            issue.message[:80],
        )

    console.print(table)
    console.print(f"\n[red]Errors: {len(errors)}[/red] | "
                  f"[yellow]Warnings: {len(warnings)}[/yellow] | "
                  f"[blue]Info: {len(infos)}[/blue]")


def lint_to_json(issues: list[LintIssue]) -> str:
    """Return lint issues as JSON."""
    return json.dumps([i.to_dict() for i in issues], indent=2)
