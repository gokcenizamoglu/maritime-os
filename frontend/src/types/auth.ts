/**
 * Matches `users/serializers.py::AuthenticatedUserSerializer` exactly —
 * the shared response shape of both `POST /api/auth/login/` and
 * `GET /api/auth/me/`.
 */
export interface AuthenticatedUserTenant {
  id: number;
  name: string;
}

export interface AuthenticatedUserRole {
  id: number;
  name: string;
}

export interface AuthenticatedUser {
  id: number;
  username: string;
  first_name: string;
  last_name: string;
  /** @deprecated Temporary field from User.role — use `capabilities` instead. */
  role: string;
  tenant: AuthenticatedUserTenant | null;
  roles: AuthenticatedUserRole[];
  capabilities: string[];
}
