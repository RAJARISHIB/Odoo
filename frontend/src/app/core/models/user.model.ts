/** Mirrors `apps/users/models.py::User.to_dict()`. */
export type Role = 'super_admin' | 'admin' | 'hr' | 'manager' | 'employee';
export type UserStatus = 'active' | 'invited' | 'suspended' | 'archived';
export type Panel = 'admin' | 'user';

/** Roles that land in the admin panel - keep in sync with `Role.ADMIN_PANEL`. */
export const ADMIN_ROLES: Role[] = ['super_admin', 'admin', 'hr', 'manager'];

/**
 * `User.role` is typed below as a plain slug because that's how most of the
 * app treats it, but `apps/users/models.py::User.to_dict()` actually returns
 * `{id, name, slug}` once a role is a real document (which, post-RBAC
 * migration, it always is) - `role: Role` on the interface is aspirational,
 * not what the wire sends. Untyped input on purpose: this narrows either
 * shape down to the slug, for the couple of call sites that got bitten by
 * the mismatch (a `.replace()` on an object throws). It does not paper over
 * every affected call site - most of the app still compares/displays
 * `user.role` directly assuming a string, which is the same bug lying
 * dormant; this is a targeted fix, not a full audit.
 */
export function roleSlug(role: unknown): Role {
  if (typeof role === 'string') return role as Role;
  return (role as { slug?: Role } | null | undefined)?.slug ?? 'employee';
}

export interface User {
  id: string;
  /** System-generated sign-in ID, e.g. OIJODO20220001. Never editable. */
  login_id: string;
  email: string;
  first_name: string;
  last_name: string;
  full_name: string;
  phone?: string | null;
  avatar_url?: string | null;
  employee_id?: string | null;
  designation?: string | null;
  date_of_joining?: string | null;
  /** YYYY-MM-DD, or null. Editable by an admin from the user's edit page. */
  date_of_birth?: string | null;
  role: Role;
  status: UserStatus;
  panel: Panel;
  is_admin: boolean;
  organization_id?: string;
  department_id?: string | null;
  last_login_at?: string | null;
  must_change_password?: boolean;
  email_verified?: boolean;
  mfa_enabled?: boolean;
  created_at?: string;
  /** Present only in the response that creates a user. */
  temporary_password?: string;
}

export interface AuthTokens {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_at: string;
  expires_in: number;
}

export interface Permissions {
  panel: Panel;
  /** True until the user replaces a system-generated password. */
  must_change_password: boolean;
  can_manage_users: boolean;
  can_manage_organization: boolean;
  can_view_all_attendance: boolean;
  can_approve_attendance: boolean;
  /**
   * Fine-grained `module.action` flags from `core.constants.Permissions` -
   * e.g. `permissions['audit.view']`, `permissions['roles.manage']`. Indexed
   * rather than named individually so the frontend never has to be extended
   * just because the backend added a new permission string.
   */
  [permission: string]: boolean | Panel | undefined;
}

/**
 * What `POST /auth/login` returns.  For an MFA-enabled account this is only
 * the `mfa_required` branch - no tokens, no user - until `Auth.verifyMfa`
 * completes the sign-in. See `apps.users.services.login`.
 */
export interface LoginResponse {
  mfa_required: boolean;
  user?: User;
  tokens?: AuthTokens;
  realtime?: { channels: string[] };
  mfa_pending_token?: string;
  expires_at?: string;
}

/** Narrowed shape once a session has actually been established. */
export interface AuthenticatedSession {
  user: User;
  tokens: AuthTokens;
  realtime?: { channels: string[] };
}

export interface Session {
  id: string;
  created_at: string | null;
  expires_at: string | null;
  ip_address: string;
  user_agent: string;
  is_current: boolean;
}

export interface MfaEnrollStart {
  secret: string;
  otpauth_uri: string;
  qr_svg: string;
}

export interface MfaEnrollConfirm {
  recovery_codes: string[];
}

export interface SessionResponse {
  user: User;
  organization: Organization | null;
  permissions: Permissions;
  realtime?: { channels: string[] };
}

export interface Organization {
  id: string;
  name: string;
  slug: string;
  /** Two-letter prefix of every login ID issued here ("Odoo India" -> "OI"). */
  code: string;
  logo_url?: string | null;
  email: string;
  phone?: string | null;
  city?: string | null;
  country?: string | null;
  timezone: string;
  work_start_time: string;
  work_end_time: string;
  full_day_hours: number;
  half_day_hours: number;
  late_grace_minutes: number;
  working_days: number[];
  is_active: boolean;
}

export interface Department {
  id: string;
  name: string;
  code?: string | null;
  description?: string | null;
  organization_id: string;
  head_id?: string | null;
  is_active: boolean;
}

export interface UserStats {
  total: number;
  active: number;
  suspended: number;
  by_role: Record<Role, number>;
}
