"""Load and normalize the OpenAPI specification."""

from __future__ import annotations

import copy
import os
import re
from pathlib import Path
from typing import Any

import yaml

_PATH_PARAM_RE = re.compile(r"\{([^}]+)\}")

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
                if not isinstance(param, dict):
                    continue
                if _resolve_parameter_name(spec, param) != "ORG":
                    continue
                if "$ref" in param:
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


def _resolve_parameter_name(spec: dict[str, Any], param: Any) -> str | None:
    ref: str | None = None
    if isinstance(param, dict):
        raw_ref = param.get("$ref")
        if isinstance(raw_ref, str):
            ref = raw_ref
        else:
            name = param.get("name")
            return name if isinstance(name, str) else None
    elif isinstance(param, str) and param.startswith("#/"):
        ref = param
    else:
        return None
    if ref and ref.startswith("#/"):
        ref_key = ref.rsplit("/", 1)[-1]
        components = spec.get("components") or {}
        params = components.get("parameters") or {}
        ref_obj = params.get(ref_key)
        if isinstance(ref_obj, dict):
            name = ref_obj.get("name")
            return name if isinstance(name, str) else None
    return None


def _path_parameter_ref(spec: dict[str, Any], name: str) -> dict[str, Any]:
    components = spec.setdefault("components", {})
    params = components.setdefault("parameters", {})
    if name in params:
        return {"$ref": f"#/components/parameters/{name}"}
    return {
        "name": name,
        "in": "path",
        "required": True,
        "style": "simple",
        "explode": False,
        "schema": {"type": "string"},
    }


def _ensure_path_parameters(spec: dict[str, Any]) -> None:
    """Postman export often omits path params; FastMCP needs them to build requests."""
    paths = spec.get("paths") or {}
    for path_template, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        path_vars = _PATH_PARAM_RE.findall(path_template)
        if not path_vars:
            continue
        for method, operation in path_item.items():
            if method.startswith("x-") or not isinstance(operation, dict):
                continue
            raw_params = operation.get("parameters")
            if raw_params is None:
                raw_params = []
                operation["parameters"] = raw_params
            if not isinstance(raw_params, list):
                continue
            declared = {
                n
                for p in raw_params
                if (n := _resolve_parameter_name(spec, p)) is not None
            }
            for name in path_vars:
                if name in declared:
                    continue
                raw_params.append(_path_parameter_ref(spec, name))
                declared.add(name)


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
    _ensure_path_parameters(spec)
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
