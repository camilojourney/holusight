"""Microsoft 365 authentication helpers for Graph connector."""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path
from typing import Any

try:
    import msal
except ImportError:  # pragma: no cover - exercised in environments without optional deps
    msal = None

logger = logging.getLogger(__name__)

DEFAULT_SCOPES = "Files.Read Mail.Read Notes.Read Sites.Read.All User.Read"
ADMIN_BLOCKED_MESSAGE = (
    "Your organization's admin must allow app registrations. Contact your IT department."
)


class M365Authenticator:
    """MSAL-backed device-code authenticator with token cache persistence."""

    # SPEC-011-001: Device code auth config is sourced from env and stored in authenticator state.
    def __init__(
        self,
        *,
        client_id: str | None = None,
        tenant_id: str | None = None,
        scopes: list[str] | None = None,
        cache_path: str | Path | None = None,
    ) -> None:
        if msal is None:
            raise RuntimeError(
                "M365 support requires optional dependency group 'm365' "
                "(install with: pip install -e '.[m365]')."
            )

        self.client_id = client_id or os.environ.get("CODESIGHT_M365_CLIENT_ID", "")
        if not self.client_id:
            raise ValueError("Missing CODESIGHT_M365_CLIENT_ID for M365 sync.")

        self.tenant_id = tenant_id or os.environ.get("CODESIGHT_M365_TENANT_ID", "common")
        scope_text = os.environ.get("CODESIGHT_M365_SCOPES", DEFAULT_SCOPES)
        self.scopes = scopes or scope_text.split()
        self.cache_path = Path(cache_path or Path.home() / ".codesight" / "m365-token-cache.json")
        self._token_cache = self._load_token_cache()
        self._app = self._build_app()

    # SPEC-011-001: Existing token cache is loaded for subsequent runs without re-authentication.
    def _load_token_cache(self) -> Any:
        cache = msal.SerializableTokenCache()
        if self.cache_path.exists():
            cache.deserialize(self.cache_path.read_text(encoding="utf-8"))
        return cache

    # SPEC-011-001: Device-code-auth token cache is persisted across sessions.
    def _save_token_cache(self) -> None:
        if not self._token_cache.has_state_changed:
            return
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(self._token_cache.serialize(), encoding="utf-8")
        os.chmod(self.cache_path, 0o600)

    # SPEC-011-001: Authentication uses delegated-device flow via MSAL public client app.
    def _build_app(self) -> Any:
        authority = f"https://login.microsoftonline.com/{self.tenant_id}"
        return msal.PublicClientApplication(
            client_id=self.client_id,
            authority=authority,
            token_cache=self._token_cache,
        )

    # SPEC-011-001: Silent token reuse is attempted before interactive device code flow.
    def get_access_token(self, *, force_refresh: bool = False) -> str:
        accounts = self._app.get_accounts()
        token_result: dict[str, Any] | None = None

        if accounts:
            token_result = self._app.acquire_token_silent(
                self.scopes,
                account=accounts[0],
                force_refresh=force_refresh,
            )

        if not token_result or "access_token" not in token_result:
            token_result = self._acquire_token_device_code()

        self._save_token_cache()
        return token_result["access_token"]

    # EDGE-011-004: Tenant policy failures surface a specific admin-guidance message.
    def _acquire_token_device_code(self) -> dict[str, Any]:
        flow = self._app.initiate_device_flow(scopes=self.scopes)
        if "user_code" not in flow:
            raise RuntimeError("Could not start Microsoft device-code flow.")

        logger.info("m365.auth.device_code")
        print(flow.get("message", "Complete Microsoft device login in your browser."))
        token_result = self._app.acquire_token_by_device_flow(flow)

        if "access_token" not in token_result:
            description = token_result.get("error_description", "")
            if "AADSTS65001" in description or token_result.get("error") == "unauthorized_client":
                raise PermissionError(ADMIN_BLOCKED_MESSAGE)
            raise RuntimeError(
                token_result.get("error_description")
                or token_result.get("error")
                or "Microsoft authentication failed."
            )

        return token_result

    # SPEC-011-001: Tenant-specific cache directory naming is derived from
    # authenticated account context.
    def tenant_hash(self) -> str:
        accounts = self._app.get_accounts()
        seed = self.tenant_id
        if accounts:
            seed = accounts[0].get("home_account_id", seed)
        return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12]
