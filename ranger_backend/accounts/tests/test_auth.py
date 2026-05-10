# ─── RANGER V3 START: auth tests ───
"""
Tests for the authentication feature.

Covers:
- /api/users/me/ — authed and unauthed
- /api/auth/token/ — login success, wrong password, inactive user, missing fields
- /api/auth/token/refresh/ — cookie present, cookie missing, after blacklist
- /api/auth/logout/ — blacklists the refresh, clears the cookie, idempotent
- /api/auth/token/ — returned response shape (access in body, refresh in cookie only)

Conventions:
- Each test class wraps one endpoint.
- We use APIClient over Django's test Client because DRF returns JSON
  responses and APIClient handles content-type automatically.
- We never assert on JWT token contents (those are simplejwt's concern)
  — only on our wrapping behavior: status codes, response shape, cookies,
  blacklist side effects.
"""
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient, APITestCase
from rest_framework_simplejwt.token_blacklist.models import (
    BlacklistedToken,
    OutstandingToken,
)

User = get_user_model()


# ─────────────────────────────────────────────────────────────────────
# Shared fixtures
# ─────────────────────────────────────────────────────────────────────

class AuthTestBase(APITestCase):
    """Common setup: a known user with a known password."""

    USERNAME = "testuser"
    PASSWORD = "TestPassword1234!"

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username=cls.USERNAME,
            email="testuser@example.com",
            password=cls.PASSWORD,
        )

    def setUp(self):
        self.client = APIClient()


# ─────────────────────────────────────────────────────────────────────
# /api/users/me/
# ─────────────────────────────────────────────────────────────────────

class UserMeTests(AuthTestBase):
    URL = "/api/users/me/"

    def test_unauthenticated_returns_401(self):
        response = self.client.get(self.URL)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn("detail", response.data)

    def test_authenticated_returns_user_payload(self):
        self.client.force_authenticate(self.user)
        response = self.client.get(self.URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Lock in the exact field set the frontend depends on.
        expected_keys = {
            "id", "username", "email", "organization", "groups",
            "permissions", "is_superuser", "is_staff", "mfa_enabled", "phone",
        }
        self.assertEqual(set(response.data.keys()), expected_keys)
        self.assertEqual(response.data["username"], self.USERNAME)
        self.assertEqual(response.data["email"], "testuser@example.com")
        # Non-superuser, no groups → empty permissions list (not the
        # superuser shortcut).
        self.assertEqual(response.data["permissions"], [])
        self.assertFalse(response.data["is_superuser"])

    def test_superuser_permissions_short_circuit_to_empty_list(self):
        """Superusers get [] for permissions — frontend uses is_superuser flag."""
        admin = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="AdminPass1234!",
        )
        self.client.force_authenticate(admin)
        response = self.client.get(self.URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["is_superuser"])
        self.assertEqual(response.data["permissions"], [])


# ─────────────────────────────────────────────────────────────────────
# /api/auth/token/  (login)
# ─────────────────────────────────────────────────────────────────────

class LoginTests(AuthTestBase):
    URL = "/api/auth/token/"

    def test_valid_credentials_return_200_with_access_and_user(self):
        response = self.client.post(self.URL, {
            "username": self.USERNAME,
            "password": self.PASSWORD,
        }, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("user", response.data)
        # The whole point of Checkpoint 3: refresh is NOT in body.
        self.assertNotIn("refresh", response.data)

    def test_valid_credentials_set_refresh_cookie(self):
        response = self.client.post(self.URL, {
            "username": self.USERNAME,
            "password": self.PASSWORD,
        }, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("ranger_refresh", response.cookies)

        cookie = response.cookies["ranger_refresh"]
        self.assertTrue(cookie.value)  # non-empty token
        self.assertTrue(cookie["httponly"])
        self.assertEqual(cookie["samesite"], "Strict")
        self.assertEqual(cookie["path"], "/api/auth/")

    def test_wrong_password_returns_401(self):
        response = self.client.post(self.URL, {
            "username": self.USERNAME,
            "password": "wrong",
        }, format="json")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertNotIn("ranger_refresh", response.cookies)

    def test_unknown_user_returns_401(self):
        response = self.client.post(self.URL, {
            "username": "nobody",
            "password": "whatever",
        }, format="json")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_inactive_user_returns_401(self):
        self.user.is_active = False
        self.user.save()

        response = self.client.post(self.URL, {
            "username": self.USERNAME,
            "password": self.PASSWORD,
        }, format="json")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_missing_fields_returns_400(self):
        response = self.client.post(self.URL, {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("username", response.data)
        self.assertIn("password", response.data)

    def test_login_user_payload_matches_users_me(self):
        """The user dict in login response should match /api/users/me/ exactly."""
        login = self.client.post(self.URL, {
            "username": self.USERNAME,
            "password": self.PASSWORD,
        }, format="json")
        self.client.force_authenticate(self.user)
        me = self.client.get("/api/users/me/")

        self.assertEqual(login.data["user"], me.data)


# ─────────────────────────────────────────────────────────────────────
# /api/auth/token/refresh/
# ─────────────────────────────────────────────────────────────────────

class RefreshTests(AuthTestBase):
    URL = "/api/auth/token/refresh/"
    LOGIN_URL = "/api/auth/token/"

    def _login_and_get_cookie(self) -> str:
        """Helper: login, return the refresh cookie value."""
        response = self.client.post(self.LOGIN_URL, {
            "username": self.USERNAME,
            "password": self.PASSWORD,
        }, format="json")
        return response.cookies["ranger_refresh"].value

    def test_valid_cookie_returns_new_access(self):
        self._login_and_get_cookie()
        # APIClient persists cookies between requests automatically.
        response = self.client.post(self.URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        # Cookie was rotated.
        self.assertIn("ranger_refresh", response.cookies)

    def test_rotation_invalidates_old_refresh(self):
        """After refresh, the OLD refresh token should be blacklisted."""
        old_cookie = self._login_and_get_cookie()
        self.client.post(self.URL)  # rotate

        # Manually try to use the old token by setting it as the cookie
        self.client.cookies["ranger_refresh"] = old_cookie
        response = self.client.post(self.URL)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_no_cookie_returns_401(self):
        response = self.client.post(self.URL)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data["detail"], "No refresh token cookie.")

    def test_invalid_cookie_clears_it(self):
        self.client.cookies["ranger_refresh"] = "garbage.token.value"
        response = self.client.post(self.URL)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        # Cookie should be deleted by the response (Max-Age=0)
        self.assertEqual(response.cookies["ranger_refresh"].value, "")


# ─────────────────────────────────────────────────────────────────────
# /api/auth/logout/
# ─────────────────────────────────────────────────────────────────────

class LogoutTests(AuthTestBase):
    URL = "/api/auth/logout/"
    LOGIN_URL = "/api/auth/token/"

    def _login(self) -> str:
        """Login and return the access token. Refresh cookie is set on
        self.client automatically."""
        response = self.client.post(self.LOGIN_URL, {
            "username": self.USERNAME,
            "password": self.PASSWORD,
        }, format="json")
        return response.data["access"]

    def test_unauthenticated_returns_401(self):
        response = self.client.post(self.URL)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_returns_205_and_clears_cookie(self):
        access = self._login()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

        response = self.client.post(self.URL)
        self.assertEqual(response.status_code, status.HTTP_205_RESET_CONTENT)
        # Cookie deletion: empty value with Max-Age=0
        self.assertEqual(response.cookies["ranger_refresh"].value, "")

    def test_logout_blacklists_refresh_token(self):
        self._login()
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {self._login()}"  # fresh access
        )

        before = BlacklistedToken.objects.count()
        self.client.post(self.URL)
        after = BlacklistedToken.objects.count()

        self.assertEqual(after, before + 1)

    def test_logout_then_refresh_returns_401(self):
        """End-to-end: log in, log out, try to refresh → fail."""
        access = self._login()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        self.client.post(self.URL)
        self.client.credentials()  # clear auth header

        response = self.client.post("/api/auth/token/refresh/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_idempotent_with_no_cookie(self):
        """Logout with no refresh cookie still succeeds (clears nothing)."""
        access = self._login()
        # Clear the refresh cookie to simulate "already logged out" state
        self.client.cookies.clear()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

        response = self.client.post(self.URL)
        self.assertEqual(response.status_code, status.HTTP_205_RESET_CONTENT)
# ─── RANGER V3 END: auth tests ───