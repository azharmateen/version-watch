"""OpenAPI spec differ: compare endpoints, schemas, parameters.

Classifies changes as breaking or non-breaking.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Severity(str, Enum):
    BREAKING = "breaking"
    NON_BREAKING = "non-breaking"
    INFO = "info"


@dataclass
class Change:
    path: str
    description: str
    severity: Severity
    old_value: Any = None
    new_value: Any = None

    def to_dict(self) -> dict:
        d = {
            "path": self.path,
            "description": self.description,
            "severity": self.severity.value,
        }
        if self.old_value is not None:
            d["old_value"] = str(self.old_value)
        if self.new_value is not None:
            d["new_value"] = str(self.new_value)
        return d


@dataclass
class DiffResult:
    breaking: list[Change] = field(default_factory=list)
    non_breaking: list[Change] = field(default_factory=list)
    info: list[Change] = field(default_factory=list)

    @property
    def has_breaking(self) -> bool:
        return len(self.breaking) > 0

    @property
    def total_changes(self) -> int:
        return len(self.breaking) + len(self.non_breaking) + len(self.info)

    def add(self, change: Change) -> None:
        if change.severity == Severity.BREAKING:
            self.breaking.append(change)
        elif change.severity == Severity.NON_BREAKING:
            self.non_breaking.append(change)
        else:
            self.info.append(change)

    def to_dict(self) -> dict:
        return {
            "summary": {
                "total_changes": self.total_changes,
                "breaking": len(self.breaking),
                "non_breaking": len(self.non_breaking),
                "info": len(self.info),
            },
            "breaking_changes": [c.to_dict() for c in self.breaking],
            "non_breaking_changes": [c.to_dict() for c in self.non_breaking],
            "info_changes": [c.to_dict() for c in self.info],
        }


def _resolve_ref(spec: dict, ref: str) -> dict:
    """Resolve a $ref pointer within a spec."""
    parts = ref.lstrip("#/").split("/")
    node = spec
    for part in parts:
        node = node.get(part, {})
    return node


def _flatten_schema(spec: dict, schema: dict) -> dict:
    """Resolve $ref in a schema to get a flat dict of properties."""
    if "$ref" in schema:
        schema = _resolve_ref(spec, schema["$ref"])
    result = copy.deepcopy(schema)
    if "properties" in result:
        for prop_name, prop_val in list(result["properties"].items()):
            if "$ref" in prop_val:
                result["properties"][prop_name] = _resolve_ref(spec, prop_val["$ref"])
    return result


def _get_endpoints(spec: dict) -> dict[str, dict]:
    """Extract all endpoints as {method_path: details}."""
    endpoints = {}
    paths = spec.get("paths", {})
    for path, path_item in paths.items():
        for method in ("get", "post", "put", "patch", "delete", "head", "options"):
            if method in path_item:
                key = f"{method.upper()} {path}"
                endpoints[key] = path_item[method]
    return endpoints


def _get_schema_properties(spec: dict, schema: dict | None) -> dict[str, dict]:
    """Get flat property dict from a schema, resolving refs."""
    if not schema:
        return {}
    flat = _flatten_schema(spec, schema)
    return flat.get("properties", {})


def _get_required_fields(spec: dict, schema: dict | None) -> set[str]:
    """Get required fields from a schema."""
    if not schema:
        return set()
    if "$ref" in schema:
        schema = _resolve_ref(spec, schema["$ref"])
    return set(schema.get("required", []))


def _get_request_body_schema(spec: dict, endpoint: dict) -> dict | None:
    """Extract the main request body schema."""
    rb = endpoint.get("requestBody", {})
    content = rb.get("content", {})
    for ct in ("application/json", "application/xml", "multipart/form-data"):
        if ct in content:
            return content[ct].get("schema")
    if content:
        return next(iter(content.values()), {}).get("schema")
    return None


def _get_response_schema(spec: dict, endpoint: dict, code: str = "200") -> dict | None:
    """Extract the response schema for a given status code."""
    responses = endpoint.get("responses", {})
    resp = responses.get(code, responses.get("201", responses.get("default", {})))
    content = resp.get("content", {})
    for ct in ("application/json",):
        if ct in content:
            return content[ct].get("schema")
    if content:
        return next(iter(content.values()), {}).get("schema")
    return None


def _get_parameters(endpoint: dict) -> dict[str, dict]:
    """Get parameters as {name: param_dict}."""
    params = {}
    for p in endpoint.get("parameters", []):
        params[p["name"]] = p
    return params


def _diff_parameters(path: str, old_params: dict, new_params: dict, result: DiffResult) -> None:
    """Compare endpoint parameters."""
    for name, old_p in old_params.items():
        if name not in new_params:
            result.add(Change(
                path=f"{path}.parameters.{name}",
                description=f"Parameter '{name}' removed",
                severity=Severity.BREAKING,
                old_value=old_p,
            ))
        else:
            new_p = new_params[name]
            if old_p.get("required") != new_p.get("required"):
                if new_p.get("required") and not old_p.get("required"):
                    result.add(Change(
                        path=f"{path}.parameters.{name}",
                        description=f"Parameter '{name}' is now required",
                        severity=Severity.BREAKING,
                        old_value="optional",
                        new_value="required",
                    ))
                else:
                    result.add(Change(
                        path=f"{path}.parameters.{name}",
                        description=f"Parameter '{name}' is now optional",
                        severity=Severity.NON_BREAKING,
                        old_value="required",
                        new_value="optional",
                    ))
            old_type = old_p.get("schema", {}).get("type")
            new_type = new_p.get("schema", {}).get("type")
            if old_type and new_type and old_type != new_type:
                result.add(Change(
                    path=f"{path}.parameters.{name}",
                    description=f"Parameter '{name}' type changed from '{old_type}' to '{new_type}'",
                    severity=Severity.BREAKING,
                    old_value=old_type,
                    new_value=new_type,
                ))

    for name in new_params:
        if name not in old_params:
            sev = Severity.BREAKING if new_params[name].get("required") else Severity.NON_BREAKING
            result.add(Change(
                path=f"{path}.parameters.{name}",
                description=f"Parameter '{name}' added" + (" (required)" if new_params[name].get("required") else " (optional)"),
                severity=sev,
                new_value=new_params[name],
            ))


def _diff_schema_fields(
    path: str,
    direction: str,
    old_spec: dict,
    new_spec: dict,
    old_schema: dict | None,
    new_schema: dict | None,
    result: DiffResult,
) -> None:
    """Compare request/response schema fields."""
    old_props = _get_schema_properties(old_spec, old_schema)
    new_props = _get_schema_properties(new_spec, new_schema)
    old_required = _get_required_fields(old_spec, old_schema)
    new_required = _get_required_fields(new_spec, new_schema)

    for fname in old_props:
        if fname not in new_props:
            if direction == "response":
                result.add(Change(
                    path=f"{path}.{direction}.{fname}",
                    description=f"Response field '{fname}' removed",
                    severity=Severity.BREAKING,
                    old_value=old_props[fname],
                ))
            else:
                result.add(Change(
                    path=f"{path}.{direction}.{fname}",
                    description=f"Request field '{fname}' removed",
                    severity=Severity.NON_BREAKING,
                    old_value=old_props[fname],
                ))
        else:
            old_type = old_props[fname].get("type")
            new_type = new_props[fname].get("type")
            if old_type and new_type and old_type != new_type:
                result.add(Change(
                    path=f"{path}.{direction}.{fname}",
                    description=f"Field '{fname}' type changed from '{old_type}' to '{new_type}'",
                    severity=Severity.BREAKING,
                    old_value=old_type,
                    new_value=new_type,
                ))

    for fname in new_props:
        if fname not in old_props:
            if direction == "request" and fname in new_required:
                result.add(Change(
                    path=f"{path}.{direction}.{fname}",
                    description=f"Required request field '{fname}' added",
                    severity=Severity.BREAKING,
                    new_value=new_props[fname],
                ))
            else:
                label = "request" if direction == "request" else "response"
                result.add(Change(
                    path=f"{path}.{direction}.{fname}",
                    description=f"New {label} field '{fname}' added",
                    severity=Severity.NON_BREAKING,
                    new_value=new_props[fname],
                ))


def diff_specs(old_spec: dict, new_spec: dict) -> DiffResult:
    """Compare two OpenAPI specs and return classified changes."""
    result = DiffResult()

    # Compare info version
    old_version = old_spec.get("info", {}).get("version", "")
    new_version = new_spec.get("info", {}).get("version", "")
    if old_version != new_version:
        result.add(Change(
            path="info.version",
            description=f"API version changed from '{old_version}' to '{new_version}'",
            severity=Severity.INFO,
            old_value=old_version,
            new_value=new_version,
        ))

    old_endpoints = _get_endpoints(old_spec)
    new_endpoints = _get_endpoints(new_spec)

    # Removed endpoints
    for ep in old_endpoints:
        if ep not in new_endpoints:
            result.add(Change(
                path=ep,
                description=f"Endpoint '{ep}' removed",
                severity=Severity.BREAKING,
                old_value=old_endpoints[ep].get("summary", ep),
            ))

    # Added endpoints
    for ep in new_endpoints:
        if ep not in old_endpoints:
            result.add(Change(
                path=ep,
                description=f"Endpoint '{ep}' added",
                severity=Severity.NON_BREAKING,
                new_value=new_endpoints[ep].get("summary", ep),
            ))

    # Changed endpoints
    for ep in old_endpoints:
        if ep in new_endpoints:
            old_ep = old_endpoints[ep]
            new_ep = new_endpoints[ep]

            # Check deprecation
            if not old_ep.get("deprecated") and new_ep.get("deprecated"):
                result.add(Change(
                    path=ep,
                    description=f"Endpoint '{ep}' marked as deprecated",
                    severity=Severity.INFO,
                ))

            # Parameters
            _diff_parameters(ep, _get_parameters(old_ep), _get_parameters(new_ep), result)

            # Request body
            old_rb = _get_request_body_schema(old_spec, old_ep)
            new_rb = _get_request_body_schema(new_spec, new_ep)
            if old_rb or new_rb:
                _diff_schema_fields(ep, "request", old_spec, new_spec, old_rb, new_rb, result)

            # Response
            old_resp = _get_response_schema(old_spec, old_ep)
            new_resp = _get_response_schema(new_spec, new_ep)
            if old_resp or new_resp:
                _diff_schema_fields(ep, "response", old_spec, new_spec, old_resp, new_resp, result)

    return result
