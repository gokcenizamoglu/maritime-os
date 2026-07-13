"""
Serializers for the internal authentication endpoints (users/views.py).
Kept in `users` — the app that already owns the User model — rather
than a new `auth` app, per this sprint's explicit scope.
"""
from rest_framework import serializers
from users.models import User


class LoginSerializer(serializers.Serializer):
    """
    Validates SHAPE only (both fields present, non-empty strings) — the
    actual credential check happens in the view via Django's
    authenticate(), not here. Deliberately does NOT call authenticate()
    inside validate(): DRF serializer validation errors are field-keyed
    (e.g. {"username": [...]}), which would leak WHICH field was wrong —
    a username-enumeration side channel. The view returns a single,
    generic "invalid credentials" response for every rejection reason
    instead.
    """
    username = serializers.CharField()
    password = serializers.CharField(trim_whitespace=False)


class TenantSummarySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()


class AuthenticatedUserSerializer(serializers.Serializer):
    """
    The exact, minimal fields the internal shell needs (see
    frontend/src/components/layout/Topbar.tsx). Deliberately a plain
    Serializer listing every field explicitly, NOT a ModelSerializer
    over User — a ModelSerializer risks exposing a field added to the
    model later (or, worse, the password hash) by omission-oversight
    rather than deliberate inclusion.
    """
    id = serializers.IntegerField()
    username = serializers.CharField()
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    role = serializers.CharField()
    tenant = TenantSummarySerializer(allow_null=True)

    @staticmethod
    def from_user(user: User) -> dict:
        """
        Builds the response dict directly from the User instance rather
        than `AuthenticatedUserSerializer(user).data`, since `tenant` on
        the model is a FK object (or None), not the {id, name} shape
        this serializer's output actually needs — constructing the dict
        explicitly here is clearer than a SerializerMethodField for a
        one-field transform used in exactly one place.
        """
        return {
            "id": user.id,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "role": user.role,
            "tenant": {"id": user.tenant_id, "name": user.tenant.name} if user.tenant_id else None,
        }
