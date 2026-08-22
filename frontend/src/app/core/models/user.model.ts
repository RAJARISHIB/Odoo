/** Mirrors `apps/users/models.py::User.to_dict()`. */
export type Role = 'super_admin' | 'admin' | 'hr' | 'manager' | 'employee';
export type UserStatus = 'active' | 'invited' | 'suspended' | 'archived';
export type Panel = 'admin' | 'user';

/** Roles that land in the admin panel - keep in sync with `Role.ADMIN_PANEL`. */
export const ADMIN_ROLES: Role[] = ['super_admin', 'admin', 'hr', 'manager'];

export interface User {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  full_name: string;
  phone?: string | null;
  avatar_url?: string | null;
  employee_id?: string | null;
  designation?: string | null;
  date_of_joining?: string | null;
  role: Role;
  status: UserStatus;
  panel: Panel;
  is_admin: boolean;
  organization_id?: string;
  department_id?: string | null;
  last_login_at?: string | null;
  must_change_password?: boolean;
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
  can_manage_users: boolean;
  can_manage_organization: boolean;
  can_view_all_attendance: boolean;
  can_approve_attendance: boolean;
}

export interface LoginResponse {
  user: User;
  tokens: AuthTokens;
  realtime?: { channels: string[] };
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
