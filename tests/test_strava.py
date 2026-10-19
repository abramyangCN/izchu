import time
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from izchu.config import Settings
from izchu.strava import StravaClient


def settings(tmp_path):
    return Settings(
        strava_client_id=286135,
        strava_client_secret="client-secret",
        strava_redirect_uri="http://localhost:8080/api/strava/callback",
        data_dir=tmp_path,
    )


def test_authorization_url_requests_only_read_scopes(tmp_path):
    client = StravaClient(settings(tmp_path))
    parsed = urlparse(client.authorization_url())
    query = parse_qs(parsed.query)

    assert parsed.netloc == "www.strava.com"
    assert query["scope"] == ["read,activity:read_all"]
    assert query["client_id"] == ["286135"]
    assert client.oauth_state.read()["state"] == query["state"][0]


@pytest.mark.asyncio
async def test_expired_token_is_refreshed_and_rotated(tmp_path):
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/api/v3/oauth/token":
            return httpx.Response(
                200,
                json={
                    "access_token": "new-access",
                    "refresh_token": "new-refresh",
                    "expires_at": int(time.time()) + 21600,
                },
            )
        assert request.headers["authorization"] == "Bearer new-access"
        return httpx.Response(200, json=[{"id": 123, "name": "Morning Ride"}])

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = StravaClient(settings(tmp_path), http=http)
    client.tokens.write(
        {
            "access_token": "expired-access",
            "refresh_token": "old-refresh",
            "expires_at": 1,
            "scope": "read,activity:read_all",
        }
    )

    activities = await client.activities()

    assert activities[0]["id"] == 123
    assert client.tokens.read()["refresh_token"] == "new-refresh"
    assert [request.url.path for request in requests] == [
        "/api/v3/oauth/token",
        "/api/v3/athlete/activities",
    ]
    await http.aclose()

