"""
Tests para OAuthClient.identity_exchange().

identity_exchange() canjea una identity-assertion JWT por un access_token
del IdP usando el grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest

from oauth_client import OAuthClient


class _FakeAsyncContext:
    """Context manager async fake para httpx.AsyncClient()."""

    def __init__(self, post_side_effect):
        self._post = post_side_effect

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def post(self, url, data=None, **kwargs):
        return self._post(url, data, **kwargs)


def _make_response(status: int, body: dict[str, Any]) -> MagicMock:
    """Crea un mock de respuesta httpx con raise_for_status real."""
    resp = MagicMock()
    resp.status_code = status
    resp.text = str(body)
    resp.json.return_value = body

    def _raise():
        if status >= 400:
            raise httpx.HTTPStatusError(
                f"{status} Err", request=MagicMock(), response=resp
            )
    resp.raise_for_status.side_effect = _raise
    return resp


def test_identity_exchange_existe_en_oauth_client():
    """OAuthClient debe tener un método identity_exchange."""
    client = OAuthClient()
    assert hasattr(client, "identity_exchange")
    assert callable(client.identity_exchange)


@pytest.mark.asyncio
async def test_identity_exchange_devuelve_access_token():
    """identity_exchange debe llamar al token endpoint y devolver el JSON."""
    fake_response = {
        "access_token": "eyJ.ATFAKE.xxx",
        "expires_in": 300,
        "scope": "calendar.read",
        "token_type": "Bearer",
    }
    fake_resp = _make_response(200, fake_response)

    with patch("oauth_client.httpx.AsyncClient") as MockClient:
        MockClient.return_value = _FakeAsyncContext(
            lambda url, data, **kw: fake_resp
        )

        client = OAuthClient()
        result = await client.identity_exchange(
            identity_assertion="eyJ.fake.jwt",
            scope="calendar.read",
        )

    assert result == fake_response
    assert result["access_token"] == "eyJ.ATFAKE.xxx"
    assert result["expires_in"] == 300


@pytest.mark.asyncio
async def test_identity_exchange_envia_grant_type_jwt_bearer():
    """identity_exchange debe enviar grant_type=...jwt-bearer."""
    sent_data: dict[str, Any] = {}

    def capture(url, data, **kwargs):
        sent_data["url"] = url
        sent_data["data"] = data
        return _make_response(200, {"access_token": "x", "expires_in": 60})

    with patch("oauth_client.httpx.AsyncClient") as MockClient:
        MockClient.return_value = _FakeAsyncContext(capture)

        client = OAuthClient()
        await client.identity_exchange(
            identity_assertion="eyJ.fake",
            scope="calendar.read",
        )

    assert sent_data["data"]["grant_type"] == "urn:ietf:params:oauth:grant-type:jwt-bearer"
    assert sent_data["data"]["assertion"] == "eyJ.fake"
    assert sent_data["data"]["scope"] == "calendar.read"
    assert "client_id" in sent_data["data"]
    assert "client_secret" in sent_data["data"]


@pytest.mark.asyncio
async def test_identity_exchange_propaga_error_idp():
    """Si el IdP responde con HTTP >= 400, debe lanzar HTTPStatusError."""
    fake_resp = _make_response(401, {"error": "invalid_grant"})

    with patch("oauth_client.httpx.AsyncClient") as MockClient:
        MockClient.return_value = _FakeAsyncContext(
            lambda url, data, **kw: fake_resp
        )

        client = OAuthClient()
        with pytest.raises(httpx.HTTPStatusError):
            await client.identity_exchange(
                identity_assertion="eyJ.bad",
                scope="calendar.read",
            )
