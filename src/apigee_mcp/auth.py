"""Apigee Edge OAuth2 token management (password + refresh grants)."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import httpx2

logger = logging.getLogger(__name__)

DEFAULT_TOKEN_URL = "https://login.apigee.com/oauth/token"
DEFAULT_CLIENT_BASIC = "ZWRnZWNsaTplZGdlY2xpc2VjcmV0"
DEFAULT_CACHE_PATH = Path("/data/apigee-token.json")
SKEW_SECONDS = 60


@dataclass
class TokenBundle:
    access_token: str
    refresh_token: str | None
    expires_at: float  # unix seconds

    @classmethod
    def from_response(cls, payload: dict[str, Any]) -> TokenBundle:
        expires_in = int(payload.get("expires_in", 1800))
        return cls(
            access_token=str(payload["access_token"]),
            refresh_token=payload.get("refresh_token"),
            expires_at=time.time() + expires_in,
        )

    def is_valid(self, skew: int = SKEW_SECONDS) -> bool:
        return time.time() < (self.expires_at - skew)

    def to_disk(self) -> dict[str, Any]:
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_at": self.expires_at,
        }

    @classmethod
    def from_disk(cls, data: dict[str, Any]) -> TokenBundle:
        return cls(
            access_token=str(data["access_token"]),
            refresh_token=data.get("refresh_token"),
            expires_at=float(data["expires_at"]),
        )


class ApigeeTokenManager:
    """Exchange and refresh Apigee management API tokens."""

    def __init__(
        self,
        *,
        username: str | None = None,
        password: str | None = None,
        token_url: str | None = None,
        client_basic: str | None = None,
        mfa_token: str | None = None,
        cache_path: Path | None = None,
        verify: str | bool | None = None,
    ) -> None:
        self.username = username or os.environ.get("APIGEE_USERNAME", "")
        self.password = password or os.environ.get("APIGEE_PASSWORD", "")
        self.token_url = token_url or os.environ.get(
            "APIGEE_TOKEN_URL", DEFAULT_TOKEN_URL
        )
        self.client_basic = client_basic or os.environ.get(
            "APIGEE_CLIENT_BASIC", DEFAULT_CLIENT_BASIC
        )
        self.mfa_token = mfa_token or os.environ.get("APIGEE_MFA_TOKEN")
        self.cache_path = cache_path or Path(
            os.environ.get("APIGEE_TOKEN_CACHE", str(DEFAULT_CACHE_PATH))
        )
        self.verify = verify if verify is not None else True
        self._lock = threading.Lock()
        self._bundle: TokenBundle | None = None
        self._load_cache()

    def _load_cache(self) -> None:
        if not self.cache_path.is_file():
            return
        try:
            data = json.loads(self.cache_path.read_text(encoding="utf-8"))
            bundle = TokenBundle.from_disk(data)
            if bundle.is_valid():
                self._bundle = bundle
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            logger.warning("Ignoring corrupt token cache at %s", self.cache_path)

    def _save_cache(self, bundle: TokenBundle) -> None:
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(
                json.dumps(bundle.to_disk(), indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.warning("Could not persist token cache: %s", exc)

    def _token_endpoint(self) -> str:
        url = self.token_url.rstrip("/")
        if self.mfa_token:
            sep = "&" if "?" in url else "?"
            return f"{url}{sep}mfa_token={self.mfa_token}"
        return url

    def _post_token(self, data: dict[str, str]) -> TokenBundle:
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json;charset=utf-8",
            "Authorization": f"Basic {self.client_basic}",
        }
        with httpx.Client(verify=self.verify, timeout=60.0) as client:
            response = client.post(
                self._token_endpoint(),
                headers=headers,
                data=data,
            )
        if response.status_code >= 400:
            raise RuntimeError(
                f"Apigee token request failed ({response.status_code}): "
                f"{response.text[:500]}"
            )
        payload = response.json()
        if "access_token" not in payload:
            raise RuntimeError(f"Apigee token response missing access_token: {payload}")
        return TokenBundle.from_response(payload)

    def _password_grant(self) -> TokenBundle:
        if not self.username or not self.password:
            raise RuntimeError(
                "APIGEE_USERNAME and APIGEE_PASSWORD must be set in the container environment"
            )
        return self._post_token(
            {
                "username": self.username,
                "password": self.password,
                "grant_type": "password",
            }
        )

    def _refresh_grant(self, refresh_token: str) -> TokenBundle:
        return self._post_token(
            {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            }
        )

    def ensure_bundle(self) -> TokenBundle:
        with self._lock:
            if self._bundle and self._bundle.is_valid():
                return self._bundle

            if self._bundle and self._bundle.refresh_token:
                try:
                    self._bundle = self._refresh_grant(self._bundle.refresh_token)
                    self._save_cache(self._bundle)
                    return self._bundle
                except RuntimeError:
                    logger.info("Refresh token failed; falling back to password grant")

            self._bundle = self._password_grant()
            self._save_cache(self._bundle)
            return self._bundle

    def get_access_token(self) -> str:
        return self.ensure_bundle().access_token

    def get_authorization_header(self) -> str:
        return f"Bearer {self.get_access_token()}"

    def check_credentials_configured(self) -> bool:
        return bool(self.username and self.password)

    def ping_token_endpoint(self) -> bool:
        """Light check without logging secrets (credentials must be configured)."""
        if not self.check_credentials_configured():
            return False
        try:
            self.ensure_bundle()
            return True
        except RuntimeError:
            return False

    def ping_org_access(self, org: str) -> bool:
        """Verify the token can call org-scoped Management API (not GET /organizations)."""
        org = org.strip()
        if not org:
            return False
        try:
            token = self.get_access_token()
        except RuntimeError:
            return False
        url = f"https://api.enterprise.apigee.com/v1/organizations/{org}"
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        try:
            with httpx.Client(verify=self.verify, timeout=30.0) as client:
                response = client.get(url, headers=headers)
            return response.status_code < 400
        except httpx.HTTPError:
            return False


class BearerAuth(httpx2.Auth):
    """Inject a fresh Apigee bearer token on each request."""

    def __init__(self, manager: ApigeeTokenManager) -> None:
        self._manager = manager

    def auth_flow(self, request: httpx2.Request):
        request.headers["Authorization"] = self._manager.get_authorization_header()
        yield request
