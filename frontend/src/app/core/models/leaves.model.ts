export type HolidayType = 'government' | 'organization' | 'festival' | 'optional';

export type LeaveStatus = 'PENDING' | 'APPROVED' | 'REJECTED' | 'CANCELLED';

export const HOLIDAY_TYPE_LABELS: Record<HolidayType, string> = {
  government: 'Government',
  organization: 'Company',
  festival: 'Festival',
  optional: 'Optional',
};

export const LEAVE_STATUS_LABELS: Record<LeaveStatus, string> = {
  PENDING: 'Pending',
  APPROVED: 'Approved',
  REJECTED: 'Rejected',
  CANCELLED: 'Cancelled',
};

export interface Holiday {
  id: string;
  name: string;
  date: string; // YYYY-MM-DD
  type: HolidayType;
  description?: string;
  is_active: boolean;
  /** Admin leave module additions - empty/absent applicable_roles = every role. */
  applicable_roles?: string[];
  created_by_id?: string | null;
  updated_by_id?: string | null;
}

export interface LeaveRequestEmployee {
  id: string;
  name: string;
  email: string;
  employee_id?: string | null;
  department_id?: string | null;
  role: string;
}

export interface LeaveRequest {
  id: string;
  organization: string;
  employee: string;
  start_date: string; // YYYY-MM-DD
  end_date: string;   // YYYY-MM-DD
  reason: string;
  status: LeaveStatus;
  total_days: number;
  created_at: string;
  updated_at: string;
  /** Admin leave module additions - set only once an admin has reviewed/tagged the request. */
  leave_type_id?: string | null;
  leave_type_name?: string;
  leave_type_code?: string;
  reviewed_by_id?: string | null;
  reviewed_at?: string | null;
  review_comment?: string | null;
  /** Added by the admin list endpoint so the table needs no second request. */
  employee_info?: LeaveRequestEmployee;
}

// =============================================================================
// Admin leave module - new types.  Nothing above this line changes the shape
// the employee calendar already reads.
// =============================================================================
export type LeaveAllocationFrequency = 'monthly' | 'yearly';

export interface LeaveType {
  id: string;
  organization_id: string;
  name: string;
  code: string;
  description?: string | null;
  is_paid: boolean;
  is_active: boolean;
  allow_fractional: boolean;
  min_unit: number;
  max_days_per_request?: number | null;
  requires_approval: boolean;
  color?: string | null;
}

export interface LeaveAllocationRule {
  id: string;
  organization_id: string;
  leave_type_id: string;
  role: string;
  frequency: LeaveAllocationFrequency;
  amount: number;
  effective_from: string;
  effective_to?: string | null;
  is_active: boolean;
}

export interface AllocationGenerateResult {
  period: string;
  frequency: LeaveAllocationFrequency;
  created: number;
  skipped: number;
}

export interface LeaveAdjustment {
  id: string;
  organization_id: string;
  user_id: string;
  leave_type_id: string;
  amount: number;
  reason: string;
  created_by_id: string;
  created_by_name?: string;
  created_at: string;
}

export interface LeaveTypeBalance {
  leave_type_id: string;
  leave_type_name: string;
  leave_type_code: string;
  is_paid?: boolean;
  year: number;
  allocated: number;
  used: number;
  pending: number;
  remaining: number;
  utilization_percentage: number;
}

export interface EmployeeLeaveBalanceRow {
  user_id: string;
  employee_name: string;
  employee_id?: string | null;
  department_id?: string | null;
  role: string;
  allocated: number;
  used: number;
  pending: number;
  remaining: number;
  utilization_percentage: number;
  by_type: LeaveTypeBalance[];
}

export interface LeaveDashboardSummary {
  year: number;
  total_employees: number;
  total_allocated: number;
  total_used: number;
  total_pending_days: number;
  total_remaining: number;
  total_pending_requests: number;
  rows: EmployeeLeaveBalanceRow[];
}

export interface EmployeeLeaveSummary {
  user: { id: string; full_name: string };
  year: number;
  balances: LeaveTypeBalance[];
  history: LeaveRequest[];
}

export interface LeaveBalance {
  year: number;
  month: number;
  monthly_entitlement: number;
  used_leave: number;
  pending_leave: number;
  remaining_leave: number;
}

export interface CalendarFeed {
  holidays: Holiday[];
  leaves: LeaveRequest[];
  balance: LeaveBalance;
}

export interface CreateLeavePayload {
  start_date: string;
  end_date: string;
  reason: string;
}
