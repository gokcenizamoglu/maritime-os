"""
Internal staff authentication endpoints — the Django side of the
browser -> Next.js BFF -> Django architecture (see
docs/AUTHENTICATION_ARCHITECTURE.md). Django remains the SOLE source of
truth for authentication and sessions; Next.js never re-implements any
of this — it only relays credentials collected here.

Deliberately four plain APIViews, not a ViewSet: these are four
distinct actions with different permission requirements (csrf/login
must be reachable with no prior session; logout/me require one), not
CRUD over a resource.
"""
from django.contrib.auth import authenticate, login, logout
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from users.models import User
from users.serializers import AuthenticatedUserSerializer, LoginSerializer


def _is_internal_app_eligible(user: User) -> bool:
    """
    Mirrors IsTenantMember's own rule (config/permissions.py) at LOGIN
    time, purely for UX — so a tenantless non-superuser sees a clean
    "invalid credentials" at login instead of a working login screen
    followed by 403s on every subsequent page. This does NOT replace
    IsTenantMember: every API call still re-checks it independently, on
    every request, unchanged by this sprint. Superusers are exempted
    because `User.tenant` is documented as nullable specifically for
    them — see users/models.py.
    """
    return bool(user.is_superuser or user.tenant_id)


class CsrfBootstrapView(APIView):
    """
    GET /api/auth/csrf/ — the FIRST call the BFF's login flow makes.

    `get_token(request)` both establishes (or reuses) the CSRF secret
    tied to this request's session and returns the masked token to send
    back. Calling it is also what causes a Set-Cookie for the session
    (under CSRF_USE_SESSIONS — see settings.py) to be emitted on the
    response if no session existed yet; the BFF captures that Set-Cookie
    the same way it captures the post-login one.

    AllowAny + no permission beyond that: this must be reachable with NO
    prior session, because calling it is how the pre-auth session gets
    created in the first place.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        token = get_token(request)
        return Response({"csrfToken": token})


@method_decorator(csrf_protect, name="dispatch")
class LoginView(APIView):
    """
    POST /api/auth/login/

    CSRF ENFORCEMENT — NOT DRF'S DEFAULT, DELIBERATELY OVERRIDDEN:
    `rest_framework.views.APIView.as_view()` wraps every DRF view in
    Django's `csrf_exempt`, and hands CSRF enforcement instead to
    `SessionAuthentication.enforce_csrf()` — which only runs if
    `authenticate()` already found an existing logged-in user on the
    request. At login time there IS no logged-in user yet (that's the
    entire point of this endpoint), so DRF's own CSRF path never
    triggers and this view would otherwise accept an unauthenticated
    POST with NO CSRF token at all — verified empirically while building
    this: without the `csrf_protect` decorator below, a login POST with
    no `X-CSRFToken` header succeeded. The explicit `@method_decorator
    (csrf_protect, name="dispatch")` restores Django's real,
    session-secret-based CSRF check independent of DRF's
    authentication-gated shortcut. LogoutView and MeView do NOT need
    this: both require `IsAuthenticated`, which only passes when a real
    prior session exists, so `SessionAuthentication.authenticate()`
    finds a genuine user and DRF's own `enforce_csrf()` runs normally.

    AllowAny at the permission-class level because you are, by
    definition, not authenticated yet when calling this.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = authenticate(
            request,
            username=serializer.validated_data["username"],
            password=serializer.validated_data["password"],
        )

        # Deliberately ONE generic response for every rejection reason
        # (wrong username, wrong password, inactive user, no tenant) —
        # distinguishing them in the response is a username-enumeration
        # / account-existence side channel. `user is None` already covers
        # inactive users: ModelBackend.authenticate() (the sole configured
        # AUTHENTICATION_BACKENDS entry) calls user_can_authenticate(),
        # which rejects is_active=False before ever returning a user —
        # confirmed by reading django.contrib.auth.backends.ModelBackend.
        if user is None or not _is_internal_app_eligible(user):
            return Response({"detail": "Invalid credentials."}, status=status.HTTP_400_BAD_REQUEST)

        # django.contrib.auth.login() rotates the session key (cycles to
        # a new session id) as Django's own built-in session-fixation
        # defense, and flushes any pre-auth session data — not something
        # this view implements, just relies on.
        login(request, user)

        return Response(AuthenticatedUserSerializer.from_user(user))


class LogoutView(APIView):
    """
    POST /api/auth/logout/ — requires an authenticated session (you can
    only log out a session that exists). CSRF is enforced identically to
    any other session-authenticated unsafe method.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    """GET /api/auth/me/ — the caller's own identity, nothing else."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(AuthenticatedUserSerializer.from_user(request.user))
