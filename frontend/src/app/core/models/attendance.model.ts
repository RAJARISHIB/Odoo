/** Mirrors `apps/attendance/models.py`. */
export type AttendanceStatus = 'present' | 'absent' | 'late' | 'half_day' | 'on_leave' | 'holiday';
export type AttendanceSource = 'web' | 'mobile' | 'biometric' | 'manual';

export interface WorkSession {
  check_in: string;
  check_out: string | null;
  source: AttendanceSource;
  note?: string | null;
  is_open: boolean;
  duration_seconds: number;
}

export interface Attendance {
  id: string;
  organization_id: string;
  user_id: string;
  date: string;
  sessions: WorkSession[];
  status: AttendanceStatus;
  first_check_in: string | null;
  last_check_out: string | null;
  total_seconds: number;
  total_hours: number;
  overtime_seconds: number;
  late_minutes: number;
  is_checked_in: boolean;
  is_manual: boolean;
  note?: string | null;
  /** Added by the admin list endpoint so the table needs no second request. */
  user?: { id: string; name: string; email: string; employee_id?: string | null };
}

export interface AttendanceState {
  date: string;
  is_checked_in: boolean;
  status: AttendanceStatus | null;
  total_hours: number;
  sessions: WorkSession[];
  attendance: Attendance | null;
}

export interface AttendanceSummary {
  user_id: string;
  user_name: string;
  date_from: string;
  date_to: string;
  days_recorded: number;
  total_hours: number;
  average_hours: number;
  counts: Record<AttendanceStatus, number>;
}

export interface DailyOverview {
  date: string;
  headcount: number;
  marked: number;
  not_marked: number;
  currently_checked_in: number;
  counts: Record<AttendanceStatus, number>;
  total_hours: number;
}

export const ATTENDANCE_STATUS_LABELS: Record<AttendanceStatus, string> = {
  present: 'Present',
  absent: 'Absent',
  late: 'Late',
  half_day: 'Half day',
  on_leave: 'On leave',
  holiday: 'Holiday',
};
