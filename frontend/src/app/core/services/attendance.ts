import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { Api, QueryParams } from './api';
import {
  Attendance as AttendanceRecord,
  AttendanceState,
  AttendanceSummary,
  DailyOverview,
} from '../models/attendance.model';
import { Page } from '../models/api.model';

/**
 * Attendance calls.
 *
 * The `my*` methods back the user panel; the `admin*` ones back the admin panel
 * and require an admin-panel role.
 */
@Injectable({ providedIn: 'root' })
export class Attendance {
  private readonly api = inject(Api);

  // -- user panel --------------------------------------------------------
  status(): Observable<AttendanceState> {
    return this.api.get<AttendanceState>('attendance/status');
  }

  checkIn(payload: { note?: string; source?: string } = {}): Observable<AttendanceRecord> {
    return this.api.post<AttendanceRecord>('attendance/check-in', { source: 'web', ...payload });
  }

  checkOut(payload: { note?: string } = {}): Observable<AttendanceRecord> {
    return this.api.post<AttendanceRecord>('attendance/check-out', payload);
  }

  myRecords(params: QueryParams = {}): Observable<Page<AttendanceRecord>> {
    return this.api.getPage<AttendanceRecord>('attendance/me', params);
  }

  mySummary(params: QueryParams = {}): Observable<AttendanceSummary> {
    return this.api.get<AttendanceSummary>('attendance/me/summary', params);
  }

  // -- admin panel -------------------------------------------------------
  adminList(params: QueryParams = {}): Observable<Page<AttendanceRecord>> {
    return this.api.getPage<AttendanceRecord>('admin/attendance', params);
  }

  adminOverview(date?: string): Observable<DailyOverview> {
    return this.api.get<DailyOverview>('admin/attendance/overview', { date });
  }

  adminUserSummary(userId: string, params: QueryParams = {}): Observable<AttendanceSummary> {
    return this.api.get<AttendanceSummary>(`admin/attendance/users/${userId}/summary`, params);
  }

  /** Create or correct one employee's day. */
  adminManualEntry(payload: {
    user_id: string;
    date: string;
    check_in?: string;
    check_out?: string;
    status?: string;
    note?: string;
  }): Observable<AttendanceRecord> {
    return this.api.post<AttendanceRecord>('admin/attendance', payload);
  }

  adminRemove(recordId: string): Observable<unknown> {
    return this.api.delete(`admin/attendance/${recordId}`);
  }
}
