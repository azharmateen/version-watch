"""Deprecation tracker: scan OpenAPI spec for deprecated fields/endpoints."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any


@dataclass
class DeprecationEntry:
    path: str
    kind: str  # "endpoint", "parameter", "field"
    description: str
    sunset_date: date | None = None
    replacement: str | None = None

    @property
    def days_until_sunset(self) -> int | None:
        if self.sunset_date is None:
            return None
        return (self.sunset_date - date.today()).days

    @property
    def is_past_sunset(self) -> bool:
        if self.sunset_date is None:
            return False
        return self.sunset_date < date.today()

    @property
    def urgency(self) -> str:
        days = self.days_until_sunset
        if days is None:
            return "unknown"
        if days < 0:
            return "expired"
        if days <= 30:
            return "critical"
        if days <= 90:
            return "warning"
        return "ok"

    def to_dict(self) -> dict:
        d = {
            "path": self.path,
            "kind": self.kind,
            "description": self.description,
            "urgency": self.urgency,
        }
        if self.sunset_date:
            d["sunset_date"] = self.sunset_date.isoformat()
            d["days_until_sunset"] = self.days_until_sunset
        if self.replacement:
            d["replacement"] = self.replacement
        return d


def _parse_sunset_date(value: Any) -> date | None:
    """Parse a sunset date from various formats."""
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%m/%d/%Y"):
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                continue
    return None


def _extract_replacement(description: str | None) -> str | None:
    """Try to extract replacement info from description text."""
    if not description:
        return None
    desc_lower = description.lower()
    for marker in ("use ", "replaced by ", "migrate to ", "see "):
        idx = desc_lower.find(marker)
        if idx >= 0:
            return description[idx:].strip().rstrip(".")
    return None


def _resolve_ref(spec: dict, ref: str) -> dict:
    parts = ref.lstrip("#/").split("/")
    node = spec
    for part in parts:
        node = node.get(part, {})
    return node


def _scan_schema_deprecated(
    spec: dict,
    schema: dict | None,
    base_path: str,
    results: list[DeprecationEntry],
) -> None:
    """Scan a schema for deprecated properties."""
    if not schema:
        return
    if "$ref" in schema:
        schema = _resolve_ref(spec, schema["$ref"])

    for prop_name, prop_val in schema.get("properties", {}).items():
        if "$ref" in prop_val:
            prop_val = _resolve_ref(spec, prop_val["$ref"])
        if prop_val.get("deprecated"):
            sunset = _parse_sunset_date(prop_val.get("x-sunset-date"))
            desc = prop_val.get("description", f"Field '{prop_name}' is deprecated")
            results.append(DeprecationEntry(
                path=f"{base_path}.{prop_name}",
                kind="field",
                description=desc,
                sunset_date=sunset,
                replacement=_extract_replacement(desc),
            ))


def scan_deprecations(spec: dict) -> list[DeprecationEntry]:
    """Scan an OpenAPI spec for all deprecated items."""
    results: list[DeprecationEntry] = []

    paths = spec.get("paths", {})
    for path, path_item in paths.items():
        for method in ("get", "post", "put", "patch", "delete", "head", "options"):
            if method not in path_item:
                continue
            operation = path_item[method]
            ep_path = f"{method.upper()} {path}"

            # Deprecated endpoint
            if operation.get("deprecated"):
                sunset = _parse_sunset_date(operation.get("x-sunset-date"))
                desc = operation.get("summary", "") or operation.get("description", "")
                if not desc:
                    desc = f"Endpoint {ep_path} is deprecated"
                results.append(DeprecationEntry(
                    path=ep_path,
                    kind="endpoint",
                    description=desc,
                    sunset_date=sunset,
                    replacement=_extract_replacement(desc),
                ))

            # Deprecated parameters
            for param in operation.get("parameters", []):
                if param.get("deprecated"):
                    sunset = _parse_sunset_date(param.get("x-sunset-date"))
                    desc = param.get("description", f"Parameter '{param['name']}' is deprecated")
                    results.append(DeprecationEntry(
                        path=f"{ep_path}.parameters.{param['name']}",
                        kind="parameter",
                        description=desc,
                        sunset_date=sunset,
                        replacement=_extract_replacement(desc),
                    ))

            # Request body schema fields
            rb = operation.get("requestBody", {})
            for ct, ct_val in rb.get("content", {}).items():
                _scan_schema_deprecated(spec, ct_val.get("schema"), f"{ep_path}.request", results)

            # Response schema fields
            for code, resp in operation.get("responses", {}).items():
                for ct, ct_val in resp.get("content", {}).items():
                    _scan_schema_deprecated(spec, ct_val.get("schema"), f"{ep_path}.response[{code}]", results)

    # Top-level component schemas
    for schema_name, schema_val in spec.get("components", {}).get("schemas", {}).items():
        _scan_schema_deprecated(spec, schema_val, f"#/components/schemas/{schema_name}", results)

    return results
