# ─── RANGER V3 START: auth views ───
"""
Auth views.

UserMeView is the read-only "who am I" endpoint. Login, logout, and refresh
land in this file in later checkpoints.
"""
from rest_framework import generics, permissions
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import CustomUser
from .serializers import CustomTokenObtainPairSerializer, UserMeSerializer


class UserMeView(generics.RetrieveAPIView):
    """
    GET /api/users/me/

    Returns the authenticated user's profile, organization, groups, and
    flattened permissions list. The frontend hydrates its auth store from
    this on app load and after login.
    """

    serializer_class = UserMeSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_object(self) -> CustomUser:
        # Always return the requesting user — no lookup by ID. This is a
        # "self" endpoint by design; users can never query other users here.
        return self.request.user



class CustomTokenObtainPairView(TokenObtainPairView):
    """
    POST /api/auth/token/

    Login endpoint. On success returns {access, user} in the body and sets
    the refresh token in an httpOnly cookie (see settings.REFRESH_COOKIE).
    On failure (wrong password, inactive user), returns 401.
    """

    serializer_class = CustomTokenObtainPairSerializer

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code == 200 and "refresh" in response.data:
            refresh_token = response.data.pop("refresh")
            _set_refresh_cookie(response, refresh_token)
        return response
# ─── RANGER V3 END: auth views ───

# ─── RANGER V3 START: auth cookie helpers ───
from django.conf import settings
from rest_framework.response import Response


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    """Attach the refresh token to the response as an httpOnly cookie.

    'secure' is computed here, not in REFRESH_COOKIE config, because
    base.py is loaded before development.py flips DEBUG to True. Reading
    settings.DEBUG at request time gives the right answer in every env.
    """
    cfg = settings.REFRESH_COOKIE
    response.set_cookie(
        key=cfg["name"],
        value=str(refresh_token),
        max_age=cfg["max_age"],
        path=cfg["path"],
        secure=not settings.DEBUG,
        httponly=cfg["httponly"],
        samesite=cfg["samesite"],
    )


def _delete_refresh_cookie(response: Response) -> None:
    """Clear the refresh cookie. Used by logout and on refresh failure."""
    cfg = settings.REFRESH_COOKIE
    response.delete_cookie(
        key=cfg["name"],
        path=cfg["path"],
        samesite=cfg["samesite"],
    )
# ─── RANGER V3 END: auth cookie helpers ───


# ─── RANGER V3 START: auth refresh + logout views ───
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken


class CookieTokenRefreshView(APIView):
    """
    POST /api/auth/token/refresh/

    Reads the refresh token from the httpOnly cookie, returns a new access
    token in the body, and rotates the refresh cookie. The frontend never
    needs to send anything in the body — the browser sends the cookie
    automatically.

    Returns 401 if the cookie is missing, expired, blacklisted, or invalid.
    On 401, the refresh cookie is cleared so a stale cookie doesn't keep
    triggering doomed retries.
    """

    permission_classes = (AllowAny,)

    def post(self, request, *args, **kwargs):
        cookie_name = settings.REFRESH_COOKIE["name"]
        refresh_token = request.COOKIES.get(cookie_name)
        if not refresh_token:
            return Response(
                {"detail": "No refresh token cookie."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # Reuse simplejwt's serializer to validate + (with rotation enabled)
        # produce a new access AND a new refresh token.
        serializer = TokenRefreshSerializer(data={"refresh": refresh_token})
        try:
            serializer.is_valid(raise_exception=True)
        except (InvalidToken, TokenError) as exc:
            response = Response(
                {"detail": str(exc)},
                status=status.HTTP_401_UNAUTHORIZED,
            )
            _delete_refresh_cookie(response)
            return response

        validated = serializer.validated_data
        # validated["access"] is always present.
        # validated["refresh"] is present because ROTATE_REFRESH_TOKENS=True
        # in settings. If someone ever flips that off, we still want this
        # endpoint to work — fall back gracefully.
        new_refresh = validated.get("refresh")

        response = Response(
            {"access": validated["access"]},
            status=status.HTTP_200_OK,
        )
        if new_refresh:
            _set_refresh_cookie(response, new_refresh)
        return response


class LogoutView(APIView):
    """
    POST /api/auth/logout/

    Blacklists the refresh token (so it can't be used again) and clears
    the cookie. Idempotent: succeeds even if no cookie was present, so
    a frontend logout button always "works" from the user's POV.

    Note on stateless JWT: the *access* token stays valid until its
    natural expiry (default 15 min). We can't invalidate it server-side
    without keeping a denylist for access tokens too, which defeats the
    point of stateless JWT. The 15-min ceiling is the trade-off.
    """

    permission_classes = (IsAuthenticated,)

    def post(self, request, *args, **kwargs):
        cookie_name = settings.REFRESH_COOKIE["name"]
        refresh_token = request.COOKIES.get(cookie_name)

        if refresh_token:
            try:
                token = RefreshToken(refresh_token)
                token.blacklist()
            except (InvalidToken, TokenError):
                # Cookie was malformed or already blacklisted. Don't fail
                # logout — just clear the cookie and move on.
                pass

        response = Response(status=status.HTTP_205_RESET_CONTENT)
        _delete_refresh_cookie(response)
        return response
# ─── RANGER V3 END: auth refresh + logout views ───

