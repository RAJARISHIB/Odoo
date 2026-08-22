export type HolidayType = 'government' | 'organization';

export type LeaveStatus = 'PENDING' | 'APPROVED' | 'REJECTED' | 'CANCELLED';

export interface Holiday {
  id: string;
  name: string;
  date: string; // YYYY-MM-DD
  type: HolidayType;
  description?: string;
  is_active: boolean;
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
