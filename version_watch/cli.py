"""Click CLI for version-watch."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import click
import yaml

from . import __version__
from .deprecation import scan_deprecations
from .differ import diff_specs
from .linter import LintLevel, lint_spec
from .planner import generate_sunset_plan
from .reporter import (
    deprecations_to_json,
    diff_to_json,
    diff_to_markdown,
    diff_to_pr_description,
    lint_to_json,
    print_deprecations_terminal,
    print_diff_terminal,
    print_lint_terminal,
)


def _load_spec(path: str) -> dict:
    """Load an OpenAPI spec from YAML or JSON."""
    p = Path(path)
    if not p.exists():
        click.echo(f"Error: File not found: {path}", err=True)
        sys.exit(1)
    text = p.read_text(encoding="utf-8")
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError as e:
        click.echo(f"Error: Failed to parse {path}: {e}", err=True)
        sys.exit(1)


@click.group()
@click.version_option(version=__version__)
def cli() -> None:
    """version-watch: API versioning manager.

    Detect breaking changes, track deprecations, and generate sunset plans.
    """


@cli.command()
@click.argument("old_spec", type=click.Path(exists=True))
@click.argument("new_spec", type=click.Path(exists=True))
@click.option("--format", "fmt", type=click.Choice(["terminal", "json", "markdown", "pr"]),
              default="terminal", help="Output format")
@click.option("--output", "-o", type=click.Path(), help="Write output to file")
def diff(old_spec: str, new_spec: str, fmt: str, output: str | None) -> None:
    """Compare two OpenAPI specs and classify changes.

    OLD_SPEC and NEW_SPEC are paths to OpenAPI YAML/JSON files.
    """
    old = _load_spec(old_spec)
    new = _load_spec(new_spec)
    result = diff_specs(old, new)

    if fmt == "terminal":
        print_diff_terminal(result)
    elif fmt == "json":
        text = diff_to_json(result)
        if output:
            Path(output).write_text(text, encoding="utf-8")
            click.echo(f"Written to {output}")
        else:
            click.echo(text)
    elif fmt == "markdown":
        text = diff_to_markdown(result)
        if output:
            Path(output).write_text(text, encoding="utf-8")
            click.echo(f"Written to {output}")
        else:
            click.echo(text)
    elif fmt == "pr":
        text = diff_to_pr_description(result)
        if output:
            Path(output).write_text(text, encoding="utf-8")
            click.echo(f"Written to {output}")
        else:
            click.echo(text)

    if result.has_breaking:
        sys.exit(1)


@cli.command()
@click.argument("spec_file", type=click.Path(exists=True))
@click.option("--format", "fmt", type=click.Choice(["terminal", "json"]),
              default="terminal", help="Output format")
def deprecated(spec_file: str, fmt: str) -> None:
    """Show deprecated endpoints and fields in an OpenAPI spec.

    SPEC_FILE is the path to an OpenAPI YAML/JSON file.
    """
    spec = _load_spec(spec_file)
    entries = scan_deprecations(spec)

    if fmt == "terminal":
        print_deprecations_terminal(entries)
    else:
        click.echo(deprecations_to_json(entries))

    expired = [e for e in entries if e.is_past_sunset]
    if expired:
        click.echo(f"\nWarning: {len(expired)} item(s) past sunset date!", err=True)


@cli.command()
@click.argument("old_spec", type=click.Path(exists=True))
@click.argument("new_spec", type=click.Path(exists=True))
@click.option("--sunset-date", type=str, default=None,
              help="Sunset date (YYYY-MM-DD). Defaults to 180 days from now.")
@click.option("--output", "-o", type=click.Path(), help="Write plan to file")
def plan(old_spec: str, new_spec: str, sunset_date: str | None, output: str | None) -> None:
    """Generate a sunset migration plan from two API versions.

    OLD_SPEC and NEW_SPEC are paths to OpenAPI YAML/JSON files.
    """
    old = _load_spec(old_spec)
    new = _load_spec(new_spec)
    result = diff_specs(old, new)

    sd = None
    if sunset_date:
        try:
            sd = datetime.strptime(sunset_date, "%Y-%m-%d").date()
        except ValueError:
            click.echo(f"Error: Invalid date format: {sunset_date}. Use YYYY-MM-DD.", err=True)
            sys.exit(1)

    plan_md = generate_sunset_plan(old, new, result, sunset_date=sd)

    if output:
        Path(output).write_text(plan_md, encoding="utf-8")
        click.echo(f"Migration plan written to {output}")
    else:
        click.echo(plan_md)


@cli.command()
@click.argument("spec_file", type=click.Path(exists=True))
@click.option("--format", "fmt", type=click.Choice(["terminal", "json"]),
              default="terminal", help="Output format")
@click.option("--fail-on-error/--no-fail-on-error", default=True,
              help="Exit with code 1 if errors found")
def lint(spec_file: str, fmt: str, fail_on_error: bool) -> None:
    """Lint an OpenAPI spec for versioning best practices.

    SPEC_FILE is the path to an OpenAPI YAML/JSON file.
    """
    spec = _load_spec(spec_file)
    issues = lint_spec(spec)

    if fmt == "terminal":
        print_lint_terminal(issues)
    else:
        click.echo(lint_to_json(issues))

    if fail_on_error and any(i.level == LintLevel.ERROR for i in issues):
        sys.exit(1)


if __name__ == "__main__":
    cli()
