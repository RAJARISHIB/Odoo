import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { Api, QueryParams } from './api';
import {
  AllocationGenerateResult,
  CalendarFeed,
  CarryForwardResult,
  CreateLeavePayload,
  EmployeeLeaveBalanceRow,
  EmployeeLeaveSummary,
  Holiday,
  LeaveAdjustment,
  LeaveAllocationRule,
  LeaveBalance,
  LeaveDashboardSummary,
  LeaveRequest,
  LeaveType,
  LeaveTypeBalance,
} from '../models/leaves.model';
import { Page } from '../models/api.model';

@Injectable({ providedIn: 'root' })
export class Leaves {
  private readonly api = inject(Api);

  getCalendar(params: QueryParams = {}): Observable<CalendarFeed> {
    return this.api.get<CalendarFeed>('leaves/calendar', params);
  }

  getHolidays(params: QueryParams = {}): Observable<Holiday[]> {
    return this.api.get<Holiday[]>('leaves/holidays', params);
  }

  getBalance(params: QueryParams = {}): Observable<LeaveBalance> {
    return this.api.get<LeaveBalance>('leaves/balance', params);
  }

  /** Per-leave-type balance for the signed-in employee - what the apply form
   * shows and checks against before submitting. */
  getTypeBalances(params: QueryParams = {}): Observable<LeaveTypeBalance[]> {
    return this.api.get<LeaveTypeBalance[]>('leaves/type-balances', params);
  }

  getMyRequests(params: QueryParams = {}): Observable<Page<LeaveRequest>> {
    return this.api.getPage<LeaveRequest>('leaves/requests', params);
  }

  applyLeave(payload: CreateLeavePayload): Observable<LeaveRequest> {
    return this.api.post<LeaveRequest>('leaves/requests', payload);
  }

  cancelLeave(requestId: string): Observable<LeaveRequest> {
    return this.api.post<LeaveRequest>(`leaves/requests/${requestId}/cancel`);
  }

  // ===========================================================================
  // Admin leave module - additive.  Everything above is unchanged.
  // ===========================================================================
  // -- leave types (shared reads; admin-only writes enforced server-side) ---
  types(params: QueryParams = {}): Observable<LeaveType[]> {
    return this.api.get<LeaveType[]>('leaves/types', params);
  }

  createType(payload: Partial<LeaveType>): Observable<LeaveType> {
    return this.api.post<LeaveType>('leaves/types', payload);
  }

  updateType(id: string, payload: Partial<LeaveType>): Observable<LeaveType> {
    return this.api.put<LeaveType>(`leaves/types/${id}`, payload);
  }

  setTypeActive(id: string, active: boolean): Observable<LeaveType> {
    return this.api.post<LeaveType>(`leaves/types/${id}/${active ? 'activate' : 'deactivate'}`, {});
  }

  // -- admin: holidays --------------------------------------------------------
  createHoliday(payload: Partial<Holiday>): Observable<Holiday> {
    return this.api.post<Holiday>('admin/leaves/holidays', payload);
  }

  updateHoliday(id: string, payload: Partial<Holiday>): Observable<Holiday> {
    return this.api.put<Holiday>(`admin/leaves/holidays/${id}`, payload);
  }

  // -- admin: requests ----------------------------------------------------
  adminRequests(params: QueryParams = {}): Observable<Page<LeaveRequest>> {
    return this.api.getPage<LeaveRequest>('admin/leaves/requests', params);
  }

  approveRequest(id: string, leaveTypeId?: string): Observable<LeaveRequest> {
    return this.api.post<LeaveRequest>(`admin/leaves/requests/${id}/approve`, { leave_type_id: leaveTypeId });
  }

  rejectRequest(id: string, comment?: string): Observable<LeaveRequest> {
    return this.api.post<LeaveRequest>(`admin/leaves/requests/${id}/reject`, { comment });
  }

  // -- admin: allocation rules ---------------------------------------------
  allocationRules(params: QueryParams = {}): Observable<LeaveAllocationRule[]> {
    return this.api.get<LeaveAllocationRule[]>('admin/leaves/allocation-rules', params);
  }

  createAllocationRule(payload: {
    leave_type_id: string;
    role: string;
    amount: number;
    frequency?: string;
    effective_from?: string;
  }): Observable<LeaveAllocationRule> {
    return this.api.post<LeaveAllocationRule>('admin/leaves/allocation-rules', payload);
  }

  updateAllocationRule(id: string, payload: Partial<LeaveAllocationRule>): Observable<LeaveAllocationRule> {
    return this.api.put<LeaveAllocationRule>(`admin/leaves/allocation-rules/${id}`, payload);
  }

  generateAllocations(payload: { year: number; month?: number; frequency?: 'monthly' | 'yearly' }): Observable<AllocationGenerateResult> {
    return this.api.post<AllocationGenerateResult>('admin/leaves/allocation-rules/generate', payload);
  }

  carryForward(payload: { leave_type_id: string; year: number; month?: number }): Observable<CarryForwardResult> {
    return this.api.post<CarryForwardResult>('admin/leaves/allocation-rules/carry-forward', payload);
  }

  // -- admin: adjustments ---------------------------------------------------
  adjustments(params: QueryParams = {}): Observable<LeaveAdjustment[]> {
    return this.api.get<LeaveAdjustment[]>('admin/leaves/adjustments', params);
  }

  createAdjustment(payload: {
    user_id: string;
    leave_type_id: string;
    amount: number;
    reason: string;
  }): Observable<LeaveAdjustment> {
    return this.api.post<LeaveAdjustment>('admin/leaves/adjustments', payload);
  }

  // -- admin: dashboard -----------------------------------------------------
  adminBalances(params: QueryParams = {}): Observable<EmployeeLeaveBalanceRow[]> {
    return this.api.get<EmployeeLeaveBalanceRow[]>('admin/leaves/balances', params);
  }

  dashboard(params: QueryParams = {}): Observable<LeaveDashboardSummary> {
    return this.api.get<LeaveDashboardSummary>('admin/leaves/dashboard', params);
  }

  employeeSummary(userId: string, params: QueryParams = {}): Observable<EmployeeLeaveSummary> {
    return this.api.get<EmployeeLeaveSummary>(`admin/leaves/employees/${userId}/summary`, params);
  }
}
