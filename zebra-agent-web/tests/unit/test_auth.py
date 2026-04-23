"""Unit tests for passkey (WebAuthn) authentication.

Tests registration, authentication, setup redirect, and logout flows
without requiring a real browser or WebAuthn authenticator.
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model
from zebra_agent_web.api.models import WebAuthnCredential

User = get_user_model()

_TEST_MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.contrib.auth.middleware.LoginRequiredMiddleware",
    "zebra_agent_web.middleware.SetupRedirectMiddleware",
]

pytestmark = [
    pytest.mark.django_db(transaction=True),
]

# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture(autouse=True)
def setup_middleware(settings):
    """Re-add SetupRedirectMiddleware since test_settings.py removes it to avoid SQLite locking."""
    settings.MIDDLEWARE = _TEST_MIDDLEWARE


@pytest.fixture(autouse=True)
def clear_challenge_store():
    """Clear the in-memory challenge store before each test."""
    from zebra_agent_web.api.auth_views import _challenge_store

    _challenge_store.clear()


@pytest.fixture
def test_credential(db, test_user):
    """Create a test WebAuthn credential."""
    import base64
    return WebAuthnCredential.objects.create(
        user=test_user,
        credential_id=base64.urlsafe_b64encode(b"test-credential-id").decode("ascii").rstrip("="),
        public_key=b"test-public-key",
        sign_count=0,
    )


@pytest.fixture
def client():
    """Django async test client."""
    from django.test import AsyncClient

    return AsyncClient()


# ===========================================================================
# Setup Redirect Middleware
# ===========================================================================


class TestSetupRedirectMiddleware:
    """Tests for the setup redirect middleware."""

    async def test_redirects_to_setup_when_no_users(self, client):
        """When no users exist, any request redirects to /auth/setup/."""
        response = await client.get("/")
        assert response.status_code == 302
        assert response.url == "/auth/setup/"

    async def test_allows_setup_page_when_no_users(self, client):
        """The setup page itself is accessible when no users exist."""
        response = await client.get("/auth/setup/")
        assert response.status_code == 200
        assert b"Welcome to Zebra Agent" in response.content

    async def test_allows_auth_urls_when_no_users(self, client):
        """Auth API endpoints are accessible when no users exist."""
        response = await client.post("/auth/begin-register/", {}, content_type="application/json")
        # 400 because missing username, but not redirect
        assert response.status_code == 400

    async def test_allows_static_when_no_users(self, client):
        """Static files are accessible when no users exist."""
        response = await client.get("/static/js/webauthn.js")
        # 404 or 200 depending on staticfiles config, but not redirect
        assert response.status_code != 302

    async def test_no_redirect_when_users_exist(self, client, test_user):
        """When users exist, requests proceed normally."""
        response = await client.get("/")
        # Will redirect to login (LoginRequiredMiddleware) not setup
        assert response.status_code == 302
        assert "/auth/login/" in response.url


# ===========================================================================
# Login Page
# ===========================================================================


class TestLoginPage:
    """Tests for the login page."""

    async def test_login_page_renders(self, client):
        """The login page renders correctly."""
        response = await client.get("/auth/login/")
        assert response.status_code == 200
        assert b"Sign in with Passkey" in response.content

    async def test_login_page_redirects_when_authenticated(self, authenticated_client):
        """Authenticated users are redirected away from login."""
        response = await authenticated_client.get("/auth/login/")
        assert response.status_code == 302
        assert response.url == "/"


# ===========================================================================
# Setup Page
# ===========================================================================


class TestSetupPage:
    """Tests for the first-time setup page."""

    async def test_setup_page_renders_when_no_users(self, client):
        """Setup page renders when no users exist."""
        response = await client.get("/auth/setup/")
        assert response.status_code == 200
        assert b"Register Passkey" in response.content

    async def test_setup_redirects_to_login_when_users_exist(self, client, test_user):
        """Setup page redirects to login when users already exist."""
        response = await client.get("/auth/setup/")
        assert response.status_code == 302
        assert response.url == "/auth/login/"


# ===========================================================================
# Logout
# ===========================================================================


class TestLogout:
    """Tests for logout."""

    async def test_logout_redirects_to_login(self, authenticated_client):
        """Logout redirects to the login page."""
        response = await authenticated_client.get("/auth/logout/")
        assert response.status_code == 302
        assert response.url == "/auth/login/"


# ===========================================================================
# WebAuthn Registration (API)
# ===========================================================================


class TestBeginRegister:
    """Tests for /auth/begin-register/."""

    async def test_requires_username(self, client):
        """Missing username returns 400."""
        response = await client.post(
            "/auth/begin-register/",
            {},
            content_type="application/json",
        )
        assert response.status_code == 400
        data = json.loads(response.content)
        assert "Username is required" in data["error"]

    async def test_returns_options(self, client):
        """Valid request returns WebAuthn options."""
        response = await client.post(
            "/auth/begin-register/",
            {"username": "newuser"},
            content_type="application/json",
        )
        assert response.status_code == 200
        data = json.loads(response.content)
        assert "challenge" in data
        assert "rp" in data
        assert data["rp"]["name"] == "Zebra Agent"

    async def test_requires_auth_when_users_exist(self, client, test_user):
        """When users exist, registration requires authentication."""
        response = await client.post(
            "/auth/begin-register/",
            {"username": "anotheruser"},
            content_type="application/json",
        )
        assert response.status_code == 403


class TestCompleteRegister:
    """Tests for /auth/complete-register/."""

    async def test_requires_credential(self, client):
        """Missing credential returns 400."""
        response = await client.post(
            "/auth/complete-register/",
            {"username": "newuser"},
            content_type="application/json",
        )
        assert response.status_code == 400

    async def test_requires_challenge(self, client):
        """No prior challenge returns 400."""
        response = await client.post(
            "/auth/complete-register/",
            {
                "username": "newuser",
                "credential": {"id": "abc", "rawId": "abc", "type": "public-key", "response": {}},
            },
            content_type="application/json",
        )
        assert response.status_code == 400
        data = json.loads(response.content)
        assert "challenge expired" in data["error"]

    @patch("zebra_agent_web.api.auth_views.verify_registration_response")
    @patch("zebra_agent_web.api.auth_views.parse_registration_credential_json")
    async def test_creates_user_and_credential(self, mock_parse, mock_verify, client):
        """Successful registration creates a user and stores the credential."""
        # First, begin registration to set challenge
        await client.post(
            "/auth/begin-register/",
            {"username": "newuser"},
            content_type="application/json",
        )

        # Mock verification result
        mock_result = MagicMock()
        mock_result.credential_id = b"cred-id"
        mock_result.credential_public_key = b"pub-key"
        mock_result.sign_count = 0
        mock_verify.return_value = mock_result

        response = await client.post(
            "/auth/complete-register/",
            {
                "username": "newuser",
                "credential": {
                    "id": "cred-id-b64",
                    "rawId": "cred-id-b64",
                    "type": "public-key",
                    "response": {
                        "clientDataJSON": "eyJ0ZXN0IjogdHJ1ZX0",
                        "attestationObject": "o2NmbXRkbm9uZQ",
                    },
                },
            },
            content_type="application/json",
        )

        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["success"] is True
        assert data["username"] == "newuser"

        # Verify user and credential were created
        user = User.objects.get(username="newuser")
        assert user.webauthn_credentials.count() == 1
        import base64
        expected_id = base64.urlsafe_b64encode(b"cred-id").decode("ascii").rstrip("=")
        assert user.webauthn_credentials.first().credential_id == expected_id


# ===========================================================================
# WebAuthn Authentication (API)
# ===========================================================================


class TestBeginAuthenticate:
    """Tests for /auth/begin-authenticate/."""

    async def test_returns_options(self, client):
        """Valid request returns WebAuthn authentication options."""
        response = await client.post(
            "/auth/begin-authenticate/",
            {},
            content_type="application/json",
        )
        assert response.status_code == 200
        data = json.loads(response.content)
        assert "challenge" in data
        assert "allowCredentials" in data


class TestCompleteAuthenticate:
    """Tests for /auth/complete-authenticate/."""

    async def test_requires_credential(self, client):
        """Missing credential returns 400."""
        response = await client.post(
            "/auth/complete-authenticate/",
            {},
            content_type="application/json",
        )
        assert response.status_code == 400

    async def test_requires_challenge(self, client):
        """No prior challenge returns 400."""
        response = await client.post(
            "/auth/complete-authenticate/",
            {
                "credential": {"id": "abc", "rawId": "abc", "type": "public-key", "response": {}},
            },
            content_type="application/json",
        )
        assert response.status_code == 400
        data = json.loads(response.content)
        assert "challenge expired" in data["error"]

    async def test_unknown_credential_returns_400(self, client):
        """Credential ID not in database returns 400."""
        # Begin auth to set challenge
        await client.post(
            "/auth/begin-authenticate/",
            {},
            content_type="application/json",
        )

        response = await client.post(
            "/auth/complete-authenticate/",
            {
                "credential": {
                    "id": "dW5rbm93bi1jcmVk",
                    "rawId": "dW5rbm93bi1jcmVk",
                    "type": "public-key",
                    "response": {"clientDataJSON": "eyJ0ZXN0IjogdHJ1ZX0", "signature": "abc"},
                },
            },
            content_type="application/json",
        )
        assert response.status_code == 400
        data = json.loads(response.content)
        assert "Unknown credential" in data["error"]

    @patch("zebra_agent_web.api.auth_views.verify_authentication_response")
    @patch("zebra_agent_web.api.auth_views.parse_authentication_credential_json")
    async def test_successful_authentication(
        self, mock_parse, mock_verify, client, test_credential
    ):
        """Successful authentication logs the user in."""
        # Begin auth to set challenge
        await client.post(
            "/auth/begin-authenticate/",
            {},
            content_type="application/json",
        )

        # Mock verification result
        mock_result = MagicMock()
        mock_result.new_sign_count = 1
        mock_verify.return_value = mock_result

        response = await client.post(
            "/auth/complete-authenticate/",
            {
                "credential": {
                    "id": "dGVzdC1jcmVkZW50aWFsLWlk",
                    "rawId": "dGVzdC1jcmVkZW50aWFsLWlk",
                    "type": "public-key",
                    "response": {
                        "clientDataJSON": "eyJ0ZXN0IjogdHJ1ZX0",
                        "signature": "abc",
                        "authenticatorData": "o2NmbXRkbm9uZQ",
                    },
                },
            },
            content_type="application/json",
        )

        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["success"] is True
        assert data["username"] == "testuser"

        # Verify sign count was updated
        test_credential.refresh_from_db()
        assert test_credential.sign_count == 1
        assert test_credential.last_used_at is not None


# ===========================================================================
# Protected Views
# ===========================================================================


class TestProtectedViews:
    """Tests that views require authentication."""

    async def test_dashboard_requires_auth(self, client, test_user):
        """Unauthenticated request to dashboard redirects to login."""
        response = await client.get("/")
        assert response.status_code == 302
        assert "/auth/login/" in response.url

    async def test_dashboard_accessible_when_authenticated(self, authenticated_client):
        """Authenticated request to dashboard succeeds."""
        response = await authenticated_client.get("/")
        # Dashboard may fail for other reasons (engine not init), but not 302
        assert response.status_code != 302

    async def test_api_health_requires_no_auth(self, client, test_user):
        """Health check endpoint is publicly accessible."""
        response = await client.get("/api/health/")
        assert response.status_code == 200

    async def test_api_metrics_requires_no_auth(self, client, test_user):
        """Metrics endpoint is publicly accessible."""
        response = await client.get("/api/metrics/")
        assert response.status_code == 200

    async def test_api_goals_requires_auth(self, client, test_user):
        """Goal execution endpoint requires authentication."""
        response = await client.post(
            "/api/goals/", {"goal": "test"}, content_type="application/json"
        )
        assert response.status_code == 403
