"""Load and normalize the OpenAPI specification."""

from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any

import yaml

# Legacy operationIds that are invalid as MCP tool names (also fixed in openapi/openapi.yaml).
_OPERATION_ID_RENAMES: dict[str, str] = {
    "KvmDelete(entireKvm)": "KvmDeleteEntireKvm",
    "EnableDebugW/oRestart": "EnableDebugWithoutRestart",
    "DisableDebugW/oRestart": "DisableDebugWithoutRestart",
    "ListOrg/envServers": "ListOrgEnvServers",
}

def _default_spec_path() -> Path:
    env = __import__("os").environ.get("APIGEE_OPENAPI_PATH")
    if env:
        return Path(env)
    container = Path("/app/openapi/openapi.yaml")
    if container.is_file():
        return container
    return Path(__file__).resolve().parents[2] / "openapi" / "openapi.yaml"


def _normalize_response_keys(spec: dict[str, Any]) -> None:
    """YAML may parse HTTP status codes as integers; OpenAPI 3 requires string keys."""
    paths = spec.get("paths") or {}
    for path_item in paths.values():
        if not isinstance(path_item, dict):
            continue
        for operation in path_item.values():
            if not isinstance(operation, dict):
                continue
            responses = operation.get("responses")
            if not isinstance(responses, dict):
                continue
            fixed: dict[str, Any] = {}
            for code, response in responses.items():
                fixed[str(code)] = response
            operation["responses"] = fixed


def _configured_org() -> str:
    return os.environ.get("APIGEE_ORG", "").strip()


def _inject_org_default(spec: dict[str, Any], org: str) -> None:
    """So MCP tools default ORG to the tenant configured in .env."""
    components = spec.get("components")
    if isinstance(components, dict):
        params = components.get("parameters")
        if isinstance(params, dict):
            org_param = params.get("ORG")
            if isinstance(org_param, dict):
                schema = org_param.setdefault("schema", {})
                if isinstance(schema, dict):
                    schema.setdefault("default", org)
                    schema.setdefault("example", org)

    paths = spec.get("paths") or {}
    for path_item in paths.values():
        if not isinstance(path_item, dict):
            continue
        for operation in path_item.values():
            if not isinstance(operation, dict):
                continue
            parameters = operation.get("parameters")
            if not isinstance(parameters, list):
                continue
            for param in parameters:
                if not isinstance(param, dict) or param.get("name") != "ORG":
                    continue
                schema = param.setdefault("schema", {})
                if isinstance(schema, dict):
                    schema.setdefault("default", org)
                    schema.setdefault("example", org)


def _prune_list_organizations(spec: dict[str, Any], _org: str) -> None:
    """GET /organizations requires system-level rights; typical org users get 403."""
    paths = spec.get("paths")
    if not isinstance(paths, dict):
        return
    item = paths.get("/organizations")
    if not isinstance(item, dict) or "get" not in item:
        return
    del item["get"]
    if not item:
        del paths["/organizations"]


def _rename_operation_ids(spec: dict[str, Any]) -> None:
    paths = spec.get("paths") or {}
    for path_item in paths.values():
        if not isinstance(path_item, dict):
            continue
        for operation in path_item.values():
            if not isinstance(operation, dict):
                continue
            op_id = operation.get("operationId")
            if op_id in _OPERATION_ID_RENAMES:
                operation["operationId"] = _OPERATION_ID_RENAMES[op_id]


def load_openapi_spec(path: Path | None = None) -> dict[str, Any]:
    spec_path = path or _default_spec_path()
    if not spec_path.is_file():
        raise FileNotFoundError(f"OpenAPI spec not found: {spec_path}")
    with spec_path.open(encoding="utf-8") as fh:
        spec = yaml.safe_load(fh)
    if not isinstance(spec, dict):
        raise ValueError("OpenAPI spec must be a mapping")
    spec = copy.deepcopy(spec)
    _normalize_response_keys(spec)
    _rename_operation_ids(spec)
    org = _configured_org()
    if org:
        _inject_org_default(spec, org)
        _prune_list_organizations(spec, org)
    return spec


def resolve_spec_path(explicit: str | None = None) -> Path:
    if explicit:
        return Path(explicit)
    env = __import__("os").environ.get("APIGEE_OPENAPI_PATH")
    if env:
        return Path(env)
    return _default_spec_path()
