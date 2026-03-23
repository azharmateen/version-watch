"""Versioning rules engine: enforce API versioning policies.

Rules check that APIs follow proper deprecation workflows,
maintain backward compatibility, and use consistent versioning.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Any

from .differ import DiffResult, Severity


class RuleVerdict(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"
    SKIP = "skip"


@dataclass
class RuleResult:
    rule_id: str
    name: str
    verdict: RuleVerdict
    message: str
    details: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = {
            "rule_id": self.rule_id,
            "name": self.name,
            "verdict": self.verdict.value,
            "message": self.message,
        }
        if self.details:
            d["details"] = self.details
        return d


@dataclass
class RuleConfig:
    """Configuration for versioning rules."""
    min_deprecation_days: int = 90
    require_sunset_header: bool = True
    require_changelog: bool = True
    max_breaking_changes_per_version: int = 10
    require_version_bump_on_breaking: bool = True
    allowed_version_schemes: list[str] = field(default_factory=lambda: ["semver", "date", "integer"])


def _parse_semver(version: str) -> tuple[int, int, int] | None:
    """Parse a semantic version string."""
    import re
    m = re.match(r"^v?(\d+)\.(\d+)\.(\d+)", version)
    if m:
        return int(m.group(1)), int(m.group(2)), int(m.group(3))
    return None


def check_no_removal_without_deprecation(
    old_spec: dict,
    new_spec: dict,
    diff_result: DiffResult,
) -> RuleResult:
    """R001: Endpoints must not be removed without prior deprecation."""
    violations = []
    old_paths = old_spec.get("paths", {})

    for change in diff_result.breaking:
        if "removed" in change.description.lower() and "endpoint" in change.description.lower():
            # Check if the endpoint was marked deprecated in the old spec
            parts = change.path.split(" ", 1)
            if len(parts) == 2:
                method, path = parts[0].lower(), parts[1]
                old_op = old_paths.get(path, {}).get(method, {})
                if not old_op.get("deprecated"):
                    violations.append(
                        f"{change.path}: removed without prior deprecation"
                    )

    if violations:
        return RuleResult(
            rule_id="R001",
            name="no-removal-without-deprecation",
            verdict=RuleVerdict.FAIL,
            message=f"{len(violations)} endpoint(s) removed without prior deprecation",
            details=violations,
        )
    return RuleResult(
        rule_id="R001",
        name="no-removal-without-deprecation",
        verdict=RuleVerdict.PASS,
        message="All removed endpoints were previously deprecated",
    )


def check_no_response_type_change(diff_result: DiffResult) -> RuleResult:
    """R002: Response field types must not change."""
    violations = []
    for change in diff_result.breaking:
        if "type changed" in change.description.lower() and "response" in change.path.lower():
            violations.append(f"{change.path}: {change.description}")

    if violations:
        return RuleResult(
            rule_id="R002",
            name="no-response-type-change",
            verdict=RuleVerdict.FAIL,
            message=f"{len(violations)} response field type change(s) detected",
            details=violations,
        )
    return RuleResult(
        rule_id="R002",
        name="no-response-type-change",
        verdict=RuleVerdict.PASS,
        message="No response field type changes detected",
    )


def check_deprecation_has_sunset(spec: dict) -> RuleResult:
    """R003: All deprecated items must have x-sunset-date."""
    violations = []
    for path, path_item in spec.get("paths", {}).items():
        for method in ("get", "post", "put", "patch", "delete", "head", "options"):
            if method not in path_item:
                continue
            op = path_item[method]
            ep = f"{method.upper()} {path}"
            if op.get("deprecated") and not op.get("x-sunset-date"):
                violations.append(f"{ep}: deprecated without x-sunset-date")
            for param in op.get("parameters", []):
                if param.get("deprecated") and not param.get("x-sunset-date"):
                    violations.append(
                        f"{ep}.parameters.{param['name']}: deprecated without x-sunset-date"
                    )

    if violations:
        return RuleResult(
            rule_id="R003",
            name="deprecation-has-sunset",
            verdict=RuleVerdict.FAIL,
            message=f"{len(violations)} deprecated item(s) missing x-sunset-date",
            details=violations,
        )
    return RuleResult(
        rule_id="R003",
        name="deprecation-has-sunset",
        verdict=RuleVerdict.PASS,
        message="All deprecated items have sunset dates",
    )


def check_sunset_date_future(spec: dict) -> RuleResult:
    """R004: Sunset dates must be in the future (or endpoint should be removed)."""
    violations = []
    today = date.today()

    for path, path_item in spec.get("paths", {}).items():
        for method in ("get", "post", "put", "patch", "delete", "head", "options"):
            if method not in path_item:
                continue
            op = path_item[method]
            ep = f"{method.upper()} {path}"
            sd = op.get("x-sunset-date")
            if sd:
                try:
                    if isinstance(sd, str):
                        sunset = datetime.strptime(sd, "%Y-%m-%d").date()
                    elif isinstance(sd, date):
                        sunset = sd
                    else:
                        continue
                    if sunset < today:
                        violations.append(
                            f"{ep}: sunset date {sunset.isoformat()} is in the past"
                        )
                except (ValueError, TypeError):
                    violations.append(f"{ep}: invalid sunset date format '{sd}'")

    if violations:
        return RuleResult(
            rule_id="R004",
            name="sunset-date-future",
            verdict=RuleVerdict.WARN,
            message=f"{len(violations)} sunset date(s) in the past",
            details=violations,
        )
    return RuleResult(
        rule_id="R004",
        name="sunset-date-future",
        verdict=RuleVerdict.PASS,
        message="All sunset dates are in the future",
    )


def check_version_bump_on_breaking(
    old_spec: dict,
    new_spec: dict,
    diff_result: DiffResult,
) -> RuleResult:
    """R005: Breaking changes require a major version bump (semver)."""
    if not diff_result.has_breaking:
        return RuleResult(
            rule_id="R005",
            name="version-bump-on-breaking",
            verdict=RuleVerdict.SKIP,
            message="No breaking changes, rule not applicable",
        )

    old_v = old_spec.get("info", {}).get("version", "")
    new_v = new_spec.get("info", {}).get("version", "")

    old_semver = _parse_semver(old_v)
    new_semver = _parse_semver(new_v)

    if old_semver is None or new_semver is None:
        return RuleResult(
            rule_id="R005",
            name="version-bump-on-breaking",
            verdict=RuleVerdict.WARN,
            message=f"Cannot parse semver: old='{old_v}', new='{new_v}'. "
                    "Cannot verify version bump.",
        )

    if new_semver[0] <= old_semver[0]:
        return RuleResult(
            rule_id="R005",
            name="version-bump-on-breaking",
            verdict=RuleVerdict.FAIL,
            message=f"Breaking changes detected but major version not bumped "
                    f"(old={old_v}, new={new_v})",
        )

    return RuleResult(
        rule_id="R005",
        name="version-bump-on-breaking",
        verdict=RuleVerdict.PASS,
        message=f"Major version bumped correctly ({old_v} -> {new_v})",
    )


def check_max_breaking_changes(
    diff_result: DiffResult,
    max_allowed: int = 10,
) -> RuleResult:
    """R006: Limit the number of breaking changes per version."""
    count = len(diff_result.breaking)
    if count > max_allowed:
        return RuleResult(
            rule_id="R006",
            name="max-breaking-changes",
            verdict=RuleVerdict.WARN,
            message=f"{count} breaking changes exceeds maximum of {max_allowed}. "
                    "Consider splitting into multiple versions.",
        )
    return RuleResult(
        rule_id="R006",
        name="max-breaking-changes",
        verdict=RuleVerdict.PASS,
        message=f"{count} breaking change(s), within limit of {max_allowed}",
    )


def run_all_rules(
    old_spec: dict | None,
    new_spec: dict,
    diff_result: DiffResult | None = None,
    config: RuleConfig | None = None,
) -> list[RuleResult]:
    """Run all versioning rules and return results."""
    if config is None:
        config = RuleConfig()

    results: list[RuleResult] = []

    # Rules that only need the new spec
    results.append(check_deprecation_has_sunset(new_spec))
    results.append(check_sunset_date_future(new_spec))

    # Rules that need diff results
    if diff_result and old_spec:
        results.append(check_no_removal_without_deprecation(old_spec, new_spec, diff_result))
        results.append(check_no_response_type_change(diff_result))
        results.append(check_version_bump_on_breaking(old_spec, new_spec, diff_result))
        results.append(check_max_breaking_changes(diff_result, config.max_breaking_changes_per_version))

    return results
