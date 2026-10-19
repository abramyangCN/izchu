import asyncio
import secrets
import time
from typing import Any
from urllib.parse import urlencode

import httpx

from .config import Settings
from .storage import JsonStore

STRAVA_API_URL = "https://www.strava.com/api/v3"
STRAVA_AUTH_URL = "https://www.strava.com/oauth/authorize"
STRAVA_TOKEN_URL = "https://www.strava.com/api/v3/oauth/token"
REQUIRED_SCOPES = {"read", "activity:read_all"}


class StravaError(RuntimeError):
    pass


class StravaClient:
    def __init__(self, settings: Settings, http: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self.tokens = JsonStore(settings.strava_token_path)
        self.oauth_state = JsonStore(settings.strava_state_path)
        self.http = http or httpx.AsyncClient(timeout=30)
        self._refresh_lock = asyncio.Lock()

    def authorization_url(self) -> str:
        if not self.settings.strava_client_id:
            raise StravaError("IZCHU_STRAVA_CLIENT_ID is not configured")
        state = secrets.token_urlsafe(32)
        self.oauth_state.write({"state": state, "created_at": int(time.time())})
        query = urlencode(
            {
                "client_id": self.settings.strava_client_id,
                "redirect_uri": self.settings.strava_redirect_uri,
                "response_type": "code",
                "approval_prompt": "force",
                "scope": "read,activity:read_all",
                "state": state,
            }
        )
        return f"{STRAVA_AUTH_URL}?{query}"

    async def exchange_code(self, code: str, state: str) -> dict[str, Any]:
        saved_state = self.oauth_state.read()
        if not saved_state or not secrets.compare_digest(saved_state.get("state", ""), state):
            raise StravaError("Invalid or expired OAuth state")
        if int(time.time()) - int(saved_state.get("created_at", 0)) > 600:
            raise StravaError("OAuth state is older than 10 minutes; start authorization again")
        payload = await self._token_request(
            {
                "client_id": self._client_id(),
                "client_secret": self._client_secret(),
                "code": code,
                "grant_type": "authorization_code",
            }
        )
        granted = set(str(payload.get("scope", "")).replace(",", " ").split())
        missing = REQUIRED_SCOPES - granted
        if missing:
            raise StravaError(f"Strava did not grant required scopes: {', '.join(sorted(missing))}")
        self.tokens.write(payload)
        self.oauth_state.delete()
        return self._safe_token_summary(payload)

    async def athlete(self) -> dict[str, Any]:
        return await self._request("GET", "/athlete")

    async def activities(
        self,
        *,
        page: int = 1,
        per_page: int = 30,
        before: int | None = None,
        after: int | None = None,
    ) -> list[dict[str, Any]]:
        params = {"page": page, "per_page": per_page}
        if before is not None:
            params["before"] = before
        if after is not None:
            params["after"] = after
        return await self._request("GET", "/athlete/activities", params=params)

    async def activity(self, activity_id: int) -> dict[str, Any]:
        return await self._request("GET", f"/activities/{activity_id}")

    async def streams(self, activity_id: int) -> dict[str, Any]:
        return await self._request(
            "GET",
            f"/activities/{activity_id}/streams",
            params={
                "keys": (
                    "time,distance,latlng,altitude,velocity_smooth,heartrate,"
                    "cadence,watts,temp,moving,grade_smooth"
                ),
                "key_by_type": "true",
            },
        )

    def status(self) -> dict[str, Any]:
        token = self.tokens.read()
        return {
            "configured": bool(
                self.settings.strava_client_id and self.settings.strava_client_secret
            ),
            "connected": token is not None,
            "athlete_id": (token or {}).get("athlete", {}).get("id"),
            "scope": (token or {}).get("scope"),
            "expires_at": (token or {}).get("expires_at"),
        }

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        access_token = await self._access_token()
        response = await self.http.request(
            method,
            f"{STRAVA_API_URL}{path}",
            headers={"Authorization": f"Bearer {access_token}"},
            **kwargs,
        )
        if response.status_code == 401:
            access_token = await self._refresh(
                force=True,
                stale_access_token=access_token,
            )
            response = await self.http.request(
                method,
                f"{STRAVA_API_URL}{path}",
                headers={"Authorization": f"Bearer {access_token}"},
                **kwargs,
            )
        if response.is_error:
            raise StravaError(f"Strava API returned {response.status_code}: {response.text[:500]}")
        return response.json()

    async def _access_token(self) -> str:
        token = self.tokens.read()
        if not token:
            raise StravaError("Strava is not connected; open /api/strava/connect first")
        if int(token.get("expires_at", 0)) <= int(time.time()) + 300:
            return await self._refresh()
        return str(token["access_token"])

    async def _refresh(
        self,
        force: bool = False,
        stale_access_token: str | None = None,
    ) -> str:
        async with self._refresh_lock:
            token = self.tokens.read()
            if not token or not token.get("refresh_token"):
                raise StravaError("No Strava refresh token is stored")
            if stale_access_token and token.get("access_token") != stale_access_token:
                return str(token["access_token"])
            if not force and int(token.get("expires_at", 0)) > int(time.time()) + 300:
                return str(token["access_token"])
            refreshed = await self._token_request(
                {
                    "client_id": self._client_id(),
                    "client_secret": self._client_secret(),
                    "grant_type": "refresh_token",
                    "refresh_token": token["refresh_token"],
                }
            )
            merged = {**token, **refreshed}
            self.tokens.write(merged)
            return str(merged["access_token"])

    async def _token_request(self, data: dict[str, Any]) -> dict[str, Any]:
        response = await self.http.post(STRAVA_TOKEN_URL, data=data)
        if response.is_error:
            raise StravaError(
                f"Strava OAuth returned {response.status_code}: {response.text[:500]}"
            )
        return response.json()

    def _client_id(self) -> int:
        if not self.settings.strava_client_id:
            raise StravaError("IZCHU_STRAVA_CLIENT_ID is not configured")
        return self.settings.strava_client_id

    def _client_secret(self) -> str:
        if not self.settings.strava_client_secret:
            raise StravaError("IZCHU_STRAVA_CLIENT_SECRET is not configured")
        return self.settings.strava_client_secret

    @staticmethod
    def _safe_token_summary(token: dict[str, Any]) -> dict[str, Any]:
        return {
            "connected": True,
            "athlete": token.get("athlete"),
            "scope": token.get("scope"),
            "expires_at": token.get("expires_at"),
        }

