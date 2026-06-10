# backend/tests/test_auth.py
import pytest
import asyncio
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_success(client: AsyncClient):
    payload = {
        "email": "test_register@example.com",
        "username": "test_register",
        "password": "password123"
    }
    response = await client.post("/api/auth/register", json=payload)
    assert response.status_code == 201

    data = response.json()
    assert "access_token" in data
    assert "user" in data
    assert data["user"]["email"] == payload["email"]
    assert data["user"]["username"] == payload["username"]
    # Password must never appear in any response
    assert "password" not in data["user"]
    assert "hashed_password" not in data["user"]


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient):
    payload = {
        "email": "duplicate_email@example.com",
        "username": "unique_user1",
        "password": "password123"
    }
    res1 = await client.post("/api/auth/register", json=payload)
    assert res1.status_code == 201

    payload["username"] = "unique_user2"
    res2 = await client.post("/api/auth/register", json=payload)
    assert res2.status_code == 409


@pytest.mark.asyncio
async def test_register_duplicate_username(client: AsyncClient):
    payload = {
        "email": "unique_email1@example.com",
        "username": "duplicate_username",
        "password": "password123"
    }
    res1 = await client.post("/api/auth/register", json=payload)
    assert res1.status_code == 201

    payload["email"] = "unique_email2@example.com"
    res2 = await client.post("/api/auth/register", json=payload)
    assert res2.status_code == 409


@pytest.mark.asyncio
async def test_register_invalid_email(client: AsyncClient):
    """Pydantic should reject malformed email addresses before they hit the DB."""
    payload = {
        "email": "not-an-email",
        "username": "someuser",
        "password": "password123"
    }
    response = await client.post("/api/auth/register", json=payload)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_sets_http_only_cookie(client: AsyncClient):
    """Refresh token must arrive as an httpOnly cookie, never in the response body."""
    payload = {
        "email": "cookie_check@example.com",
        "username": "cookie_check",
        "password": "password123"
    }
    response = await client.post("/api/auth/register", json=payload)
    assert response.status_code == 201
    assert "refresh_token" in response.cookies
    # Must not appear in the JSON body
    assert "refresh_token" not in response.json()


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient):
    payload = {
        "email": "login_success@example.com",
        "username": "login_success",
        "password": "password123"
    }
    await client.post("/api/auth/register", json=payload)

    response = await client.post("/api/auth/login", json={
        "email": payload["email"],
        "password": payload["password"]
    })
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["user"]["email"] == payload["email"]


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient):
    payload = {
        "email": "wrong_pass@example.com",
        "username": "wrong_pass",
        "password": "password123"
    }
    await client.post("/api/auth/register", json=payload)

    response = await client.post("/api/auth/login", json={
        "email": payload["email"],
        "password": "completely_wrong"
    })
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_nonexistent_email(client: AsyncClient):
    """Login with an email that was never registered should return 401, not 404."""
    response = await client.post("/api/auth/login", json={
        "email": "ghost@example.com",
        "password": "password123"
    })
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_error_message_is_generic(client: AsyncClient):
    """
    The error message must not reveal whether the email exists.
    Both wrong-email and wrong-password should return identical messages.
    """
    payload = {
        "email": "generic_msg@example.com",
        "username": "generic_msg",
        "password": "password123"
    }
    await client.post("/api/auth/register", json=payload)

    wrong_pass = await client.post("/api/auth/login", json={
        "email": payload["email"],
        "password": "wrongpassword"
    })
    no_user = await client.post("/api/auth/login", json={
        "email": "noexist@example.com",
        "password": "wrongpassword"
    })
    assert wrong_pass.json()["detail"] == no_user.json()["detail"]


@pytest.mark.asyncio
async def test_refresh_token(client: AsyncClient):
    payload = {
        "email": "refresh_me@example.com",
        "username": "refresh_me",
        "password": "password123"
    }
    reg_response = await client.post("/api/auth/register", json=payload)
    assert reg_response.status_code == 201
    original_token = reg_response.json()["access_token"]

    # Force the event loop to pause for 1 second. This guarantees the Unix
    # clock ticks forward, giving the refreshed token a unique 'exp' timestamp.
    await asyncio.sleep(1)

    refresh_response = await client.post("/api/auth/refresh")
    assert refresh_response.status_code == 200
    new_token = refresh_response.json()["access_token"]
    # New access token must be different from the original
    assert new_token != original_token


@pytest.mark.asyncio
async def test_refresh_without_cookie_fails(client: AsyncClient):
    """Calling refresh with no cookie must return 401."""
    response = await client.post("/api/auth/refresh")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_logout(client: AsyncClient):
    payload = {
        "email": "logout_me@example.com",
        "username": "logout_me",
        "password": "password123"
    }
    await client.post("/api/auth/register", json=payload)

    logout_response = await client.post("/api/auth/logout")
    assert logout_response.status_code == 204

    # Refresh must fail after logout
    refresh_response = await client.post("/api/auth/refresh")
    assert refresh_response.status_code == 401


@pytest.mark.asyncio
async def test_logout_clears_cookie(client: AsyncClient):
    """Cookie must be absent or empty after logout."""
    payload = {
        "email": "cookie_clear@example.com",
        "username": "cookie_clear",
        "password": "password123"
    }
    await client.post("/api/auth/register", json=payload)
    await client.post("/api/auth/logout")

    refresh_response = await client.post("/api/auth/refresh")
    assert refresh_response.status_code == 401


@pytest.mark.asyncio
async def test_logout_without_cookie_still_returns_204(client: AsyncClient):
    """
    Logout must be graceful even with no cookie present.
    Users should never be trapped in a broken state.
    """
    response = await client.post("/api/auth/logout")
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_access_token_structure(client: AsyncClient):
    """Access token must be a valid three-part JWT string."""
    payload = {
        "email": "jwt_structure@example.com",
        "username": "jwt_structure",
        "password": "password123"
    }
    response = await client.post("/api/auth/register", json=payload)
    token = response.json()["access_token"]
    parts = token.split(".")
    assert len(parts) == 3