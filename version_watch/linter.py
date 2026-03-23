"""API lint rules for versioning best practices."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class LintLevel(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class LintIssue:
    rule: str
    level: LintLevel
    path: str
    message: str

    def to_dict(self) -> dict:
        return {
            "rule": self.rule,
            "level": self.level.value,
            "path": self.path,
            "message": self.message,
        }


RULES = {
    "VW001": "API version in URL path",
    "VW002": "Deprecated endpoint needs sunset date",
    "VW003": "Response schema should have version field",
    "VW004": "Deprecated field should document replacement",
    "VW005": "API info must have version field",
    "VW006": "Sunset date must be in the future",
    "VW007": "No version prefix inconsistency across paths",
    "VW008": "Deprecated parameter needs sunset date",
}


def _resolve_ref(spec: dict, ref: str) -> dict:
    parts = ref.lstrip("#/").split("/")
    node = spec
    for part in parts:
        node = node.get(part, {})
    return node


def lint_spec(spec: dict) -> list[LintIssue]:
    """Lint an OpenAPI spec for versioning best practices."""
    issues: list[LintIssue] = []

    # VW005: info.version must exist
    info = spec.get("info", {})
    if not info.get("version"):
        issues.append(LintIssue(
            rule="VW005",
            level=LintLevel.ERROR,
            path="info.version",
            message="API spec must have a version in info.version",
        ))

    # VW001: Check for version in URL paths or servers
    paths = list(spec.get("paths", {}).keys())
    servers = spec.get("servers", [])
    version_pattern = re.compile(r"/v\d+")

    has_url_version = any(version_pattern.search(p) for p in paths)
    has_server_version = any(version_pattern.search(s.get("url", "")) for s in servers)

    if not has_url_version and not has_server_version:
        issues.append(LintIssue(
            rule="VW001",
            level=LintLevel.WARNING,
            path="paths",
            message="No version prefix found in URL paths (e.g., /v1/resource). "
                    "Consider using URL path versioning.",
        ))

    # VW007: Inconsistent version prefixes
    if has_url_version:
        versions_found = set()
        unversioned = []
        for p in paths:
            m = version_pattern.search(p)
            if m:
                versions_found.add(m.group())
            else:
                unversioned.append(p)
        if unversioned and versions_found:
            for p in unversioned:
                issues.append(LintIssue(
                    rule="VW007",
                    level=LintLevel.WARNING,
                    path=p,
                    message=f"Path '{p}' has no version prefix, but other paths use "
                            f"{', '.join(sorted(versions_found))}",
                ))

    # Scan endpoints
    for path, path_item in spec.get("paths", {}).items():
        for method in ("get", "post", "put", "patch", "delete", "head", "options"):
            if method not in path_item:
                continue
            operation = path_item[method]
            ep_path = f"{method.upper()} {path}"

            # VW002: Deprecated endpoint needs sunset date
            if operation.get("deprecated"):
                if not operation.get("x-sunset-date"):
                    issues.append(LintIssue(
                        rule="VW002",
                        level=LintLevel.ERROR,
                        path=ep_path,
                        message=f"Deprecated endpoint '{ep_path}' must have an x-sunset-date",
                    ))
                else:
                    # VW006: sunset date should be in the future
                    from datetime import date, datetime
                    sd = operation["x-sunset-date"]
                    try:
                        if isinstance(sd, str):
                            sunset = datetime.strptime(sd, "%Y-%m-%d").date()
                        elif isinstance(sd, date):
                            sunset = sd
                        else:
                            sunset = None
                        if sunset and sunset < date.today():
                            issues.append(LintIssue(
                                rule="VW006",
                                level=LintLevel.WARNING,
                                path=ep_path,
                                message=f"Sunset date {sunset.isoformat()} is in the past. "
                                        "Remove the endpoint or extend the sunset.",
                            ))
                    except (ValueError, TypeError):
                        pass

            # VW008: Deprecated parameter needs sunset date
            for param in operation.get("parameters", []):
                if param.get("deprecated") and not param.get("x-sunset-date"):
                    issues.append(LintIssue(
                        rule="VW008",
                        level=LintLevel.WARNING,
                        path=f"{ep_path}.parameters.{param['name']}",
                        message=f"Deprecated parameter '{param['name']}' should have an x-sunset-date",
                    ))

            # VW003: Response schema should have version field
            for code, resp in operation.get("responses", {}).items():
                for ct, ct_val in resp.get("content", {}).items():
                    schema = ct_val.get("schema", {})
                    if "$ref" in schema:
                        schema = _resolve_ref(spec, schema["$ref"])
                    props = schema.get("properties", {})
                    if props and "version" not in props and "api_version" not in props:
                        issues.append(LintIssue(
                            rule="VW003",
                            level=LintLevel.INFO,
                            path=f"{ep_path}.responses.{code}",
                            message="Response schema has no 'version' field. Consider adding one "
                                    "for client version tracking.",
                        ))

    # VW004: Deprecated fields in component schemas should document replacement
    for schema_name, schema_val in spec.get("components", {}).get("schemas", {}).items():
        for prop_name, prop_val in schema_val.get("properties", {}).items():
            if "$ref" in prop_val:
                prop_val = _resolve_ref(spec, prop_val["$ref"])
            if prop_val.get("deprecated"):
                desc = (prop_val.get("description") or "").lower()
                has_replacement = any(
                    kw in desc for kw in ("use ", "replaced by", "migrate to", "see ", "instead")
                )
                if not has_replacement:
                    issues.append(LintIssue(
                        rule="VW004",
                        level=LintLevel.WARNING,
                        path=f"#/components/schemas/{schema_name}.{prop_name}",
                        message=f"Deprecated field '{prop_name}' should document its replacement "
                                "in the description (e.g., 'Use newField instead').",
                    ))

    return issues
