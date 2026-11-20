"""Inject APIGEE_ORG into tool calls when agents omit the ORG path parameter."""

from __future__ import annotations

import os
from typing import Any

import mcp_types as mt
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.tools.base import ToolResult


class ApigeeOrgDefaultsMiddleware(Middleware):
    """Fill missing ``ORG`` from ``APIGEE_ORG`` for org-scoped Management API tools."""

    def __init__(self, org: str | None = None) -> None:
        self._org = (org or os.environ.get("APIGEE_ORG", "")).strip()

    async def on_call_tool(
        self,
        context: MiddlewareContext[mt.CallToolRequestParams],
        call_next: CallNext[mt.CallToolRequestParams, ToolResult],
    ) -> ToolResult:
        if not self._org:
            return await call_next(context)
        params = context.message
        arguments = params.arguments
        if not isinstance(arguments, dict):
            arguments = {}
            params.arguments = arguments
        if (
            "ORG" not in arguments
            and "ORG__path" not in arguments
            and "org" in arguments
        ):
            arguments["ORG"] = arguments["org"]
        if "ORG" not in arguments and "ORG__path" not in arguments:
            arguments["ORG"] = self._org
        return await call_next(context)
