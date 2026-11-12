"""FastMCP server generated from the Apigee Edge OpenAPI specification."""

from __future__ import annotations

import logging
import os
import httpx2
from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse

from apigee_mcp.auth import ApigeeTokenManager, BearerAuth
from apigee_mcp.org_defaults import ApigeeOrgDefaultsMiddleware
from apigee_mcp.spec import load_openapi_spec, resolve_spec_path

logger = logging.getLogger(__name__)

API_BASE_URL = "https://api.enterprise.apigee.com/v1"


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return int(raw)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def create_mcp(*, token_manager: ApigeeTokenManager | None = None) -> FastMCP:
    verify = os.environ.get("SSL_CERT_FILE") or os.environ.get("REQUESTS_CA_BUNDLE") or True
    manager = token_manager or ApigeeTokenManager(verify=verify)
    spec = load_openapi_spec(resolve_spec_path(os.environ.get("APIGEE_OPENAPI_PATH")))

    client = httpx2.AsyncClient(
        base_url=API_BASE_URL,
        auth=BearerAuth(manager),
        timeout=60.0,
        verify=verify,
        headers={"Accept": "application/json"},
    )

    mcp = FastMCP.from_openapi(
        openapi_spec=spec,
        client=client,
        name="Apigee Edge MCP",
    )
    if os.environ.get("APIGEE_ORG", "").strip():
        mcp.add_middleware(ApigeeOrgDefaultsMiddleware())

    @mcp.custom_route("/healthz", methods=["GET"])
    async def healthz(request: Request) -> PlainTextResponse | JSONResponse:
        token_ok: bool | None = None
        org_ok: bool | None = None
        org = os.environ.get("APIGEE_ORG", "").strip()
        if _env_bool("APIGEE_HEALTH_CHECK_TOKEN", False):
            token_ok = manager.ping_token_endpoint()
            if token_ok and org:
                org_ok = manager.ping_org_access(org)
        body = {"status": "ok", "token_ok": token_ok, "org_ok": org_ok, "org": org or None}
        if token_ok is False or org_ok is False:
            return JSONResponse(body, status_code=503)
        return JSONResponse(body)

    return mcp


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    host = os.environ.get("FASTMCP_HOST", "0.0.0.0")
    port = _env_int("FASTMCP_PORT", 18749)
    transport = os.environ.get("FASTMCP_TRANSPORT", "streamable-http")
    path = os.environ.get("FASTMCP_PATH", "/mcp")
    mcp = create_mcp()
    logger.info("Starting Apigee Edge MCP on %s:%s%s", host, port, path)
    mcp.run(transport=transport, host=host, port=port, path=path)


if __name__ == "__main__":
    main()
